"""End-to-end integration tests for Phase 5 Cloudflare R2 asset APIs."""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.storage import MockStorageProvider, get_storage


async def create_user_with_token(
    client: AsyncClient, name: str = "Test User"
) -> tuple[dict, dict[str, str]]:
    """Helper to create and authenticate a user."""
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "StrongPassword123!"
    await client.post(
        "/api/auth/signup",
        json={"display_name": name, "email": email, "password": pwd},
    )
    res = await client.post(
        "/api/auth/login",
        json={"email": email, "password": pwd},
    )
    data = res.json()
    return data["user"], {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def mock_storage(test_app: FastAPI) -> MockStorageProvider:
    """Fixture providing a clean in-memory mock storage provider."""
    storage = MockStorageProvider(bucket_name="test-r2-bucket")
    test_app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    test_app.dependency_overrides.pop(get_storage, None)


@pytest.mark.asyncio
async def test_upload_url_policy_validation(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """Validate content-type policy, size limits, and server-controlled key generation."""
    user, headers = await create_user_with_token(async_client, "Uploader")

    # 1. Valid PNG upload intent
    res_png = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "diagram.png",
            "content_type": "image/png",
            "byte_size": 1024 * 50,  # 50 KiB
            "media_type": "image",
        },
        headers=headers,
    )
    assert res_png.status_code == 201
    data_png = res_png.json()
    assert "upload_url" in data_png
    assert "asset_id" in data_png
    # Verify server-controlled object key format
    assert data_png["object_key"].startswith(f"assets/{user['id']}/")
    assert data_png["object_key"].endswith("diagram.png")

    # 2. SVG is strictly disabled (pending sanitization) -> 422
    res_svg = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "vector.svg",
            "content_type": "image/svg+xml",
            "byte_size": 2048,
            "media_type": "image",
        },
        headers=headers,
    )
    assert res_svg.status_code == 422
    assert "svg is disabled" in str(res_svg.json()).lower()

    # 3. Unsupported executable / HTML -> 422
    res_html = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "malicious.html",
            "content_type": "text/html",
            "byte_size": 1024,
            "media_type": "image",
        },
        headers=headers,
    )
    assert res_html.status_code == 422

    # 4. Oversized standard image (> 10MB) -> 400
    res_oversized = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "huge.jpg",
            "content_type": "image/jpeg",
            "byte_size": 11 * 1024 * 1024,  # 11 MiB
            "media_type": "image",
        },
        headers=headers,
    )
    assert res_oversized.status_code == 400
    assert "exceeds maximum allowed limit" in res_oversized.json()["error"]["message"]

    # 5. Unauthenticated request -> 401
    res_unauth = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "anon.png",
            "content_type": "image/png",
            "byte_size": 1024,
            "media_type": "image",
        },
    )
    assert res_unauth.status_code == 401


@pytest.mark.asyncio
async def test_asset_completion_verification(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """Completing an upload verifies storage presence and transitions status to ready."""
    user, headers = await create_user_with_token(async_client, "Completer")
    other_user, other_headers = await create_user_with_token(async_client, "Other User")

    # 1. Request upload intent
    res_intent = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "avatar.png",
            "content_type": "image/png",
            "byte_size": 4096,
            "media_type": "image",
        },
        headers=headers,
    )
    assert res_intent.status_code == 201
    asset_id = res_intent.json()["asset_id"]
    object_key = res_intent.json()["object_key"]

    # 2. Attempt completion before uploading to storage -> 400 Bad Request
    fail_res = await async_client.post(
        f"/api/assets/{asset_id}/complete",
        json={"width": 100, "height": 100},
        headers=headers,
    )
    assert fail_res.status_code == 400
    assert "not found in storage" in fail_res.json()["error"]["message"].lower()

    # 3. Simulate successful client upload into storage
    mock_storage.set_mock_object(object_key, size=4096, content_type="image/png")

    # 4. Other user cannot complete this asset -> 400
    other_res = await async_client.post(
        f"/api/assets/{asset_id}/complete",
        json={"width": 100, "height": 100},
        headers=other_headers,
    )
    assert other_res.status_code == 400

    # 5. Owner completes upload -> 200 OK
    complete_res = await async_client.post(
        f"/api/assets/{asset_id}/complete",
        json={"width": 128, "height": 128, "checksum_sha256": "a" * 64},
        headers=headers,
    )
    assert complete_res.status_code == 200
    asset_data = complete_res.json()
    assert asset_data["status"] == "ready"
    assert asset_data["width"] == 128
    assert asset_data["height"] == 128
    assert "url" in asset_data


@pytest.mark.asyncio
async def test_asset_listing_and_retrieval_permissions(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """Ready assets are listed for their owner and access-checked for unauthorized users."""
    user, headers = await create_user_with_token(async_client, "Gallery Owner")
    stranger, stranger_headers = await create_user_with_token(async_client, "Stranger")

    # Create & complete two assets: 1 image, 1 sticker
    for name, mtype, ctype in [
        ("pic.jpg", "image", "image/jpeg"),
        ("star.png", "sticker", "image/png"),
    ]:
        res = await async_client.post(
            "/api/assets/upload-url",
            json={"filename": name, "content_type": ctype, "byte_size": 2048, "media_type": mtype},
            headers=headers,
        )
        aid = res.json()["asset_id"]
        key = res.json()["object_key"]
        mock_storage.set_mock_object(key, size=2048, content_type=ctype)
        await async_client.post(f"/api/assets/{aid}/complete", json={}, headers=headers)

    # 1. List all ready assets
    list_res = await async_client.get("/api/assets", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 2

    # 2. Filter by media_type=sticker
    sticker_res = await async_client.get("/api/assets?media_type=sticker", headers=headers)
    assert sticker_res.status_code == 200
    assert sticker_res.json()["total"] == 1
    assert sticker_res.json()["items"][0]["media_type"] == "sticker"

    # 3. Stranger sees 0 assets in their own list
    stranger_list = await async_client.get("/api/assets", headers=stranger_headers)
    assert stranger_list.status_code == 200
    assert stranger_list.json()["total"] == 0

    # 4. Stranger attempting to access owner's asset directly is rejected (403)
    target_id = list_res.json()["items"][0]["id"]
    unauth_get = await async_client.get(f"/api/assets/{target_id}", headers=stranger_headers)
    assert unauth_get.status_code == 403


@pytest.mark.asyncio
async def test_safe_asset_deletion_and_referential_protection(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """Deleting an asset removes it from storage/DB, but is rejected if referenced by a board."""
    owner, h_owner = await create_user_with_token(async_client, "Asset Owner")

    # 1. Create and complete an asset
    u_res = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "badge.png",
            "content_type": "image/png",
            "byte_size": 1024,
            "media_type": "sticker",
        },
        headers=h_owner,
    )
    asset_id = u_res.json()["asset_id"]
    key = u_res.json()["object_key"]
    mock_storage.set_mock_object(key, size=1024, content_type="image/png")
    await async_client.post(f"/api/assets/{asset_id}/complete", json={}, headers=h_owner)

    # 2. Create board and attach the asset
    b_res = await async_client.post(
        "/api/boards", json={"title": "Asset Reference Board"}, headers=h_owner
    )
    board_id = b_res.json()["id"]

    attach_res = await async_client.post(
        f"/api/boards/{board_id}/assets",
        json={"asset_id": asset_id},
        headers=h_owner,
    )
    assert attach_res.status_code == 201

    # 3. Attempting to delete referenced asset fails with 409 Conflict
    del_fail = await async_client.delete(f"/api/assets/{asset_id}", headers=h_owner)
    assert del_fail.status_code == 409
    assert "currently referenced" in del_fail.json()["error"]["message"].lower()

    # 4. Create an unreferenced asset
    u_res2 = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "free.png",
            "content_type": "image/png",
            "byte_size": 512,
            "media_type": "image",
        },
        headers=h_owner,
    )
    aid2 = u_res2.json()["asset_id"]
    key2 = u_res2.json()["object_key"]
    mock_storage.set_mock_object(key2, size=512, content_type="image/png")
    await async_client.post(f"/api/assets/{aid2}/complete", json={}, headers=h_owner)

    # 5. Delete unreferenced asset succeeds (200)
    del_ok = await async_client.delete(f"/api/assets/{aid2}", headers=h_owner)
    assert del_ok.status_code == 200
    assert key2 not in mock_storage.objects

    # 6. Subsequent GET is 404
    get_404 = await async_client.get(f"/api/assets/{aid2}", headers=h_owner)
    assert get_404.status_code == 404


@pytest.mark.asyncio
async def test_board_assets_access_policy_and_attachment(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """Board members inherit access to assets attached to their boards."""
    owner, h_owner = await create_user_with_token(async_client, "Board & Asset Owner")
    viewer, h_viewer = await create_user_with_token(async_client, "Board Viewer")
    outsider, h_outsider = await create_user_with_token(async_client, "Complete Outsider")

    # 1. Create and complete asset
    u_res = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "hero_bg.webp",
            "content_type": "image/webp",
            "byte_size": 2048,
            "media_type": "background",
        },
        headers=h_owner,
    )
    asset_id = u_res.json()["asset_id"]
    key = u_res.json()["object_key"]
    mock_storage.set_mock_object(key, size=2048, content_type="image/webp")
    await async_client.post(f"/api/assets/{asset_id}/complete", json={}, headers=h_owner)

    # 2. Create board and add viewer
    b_res = await async_client.post("/api/boards", json={"title": "Shared Canvas"}, headers=h_owner)
    board_id = b_res.json()["id"]
    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": viewer["id"], "role": "viewer"},
        headers=h_owner,
    )

    # 3. Viewer attempts to attach asset -> 403 Forbidden (viewers cannot attach assets)
    v_attach = await async_client.post(
        f"/api/boards/{board_id}/assets",
        json={"asset_id": asset_id},
        headers=h_viewer,
    )
    assert v_attach.status_code == 403

    # 4. Owner attaches asset -> 201 Created
    o_attach = await async_client.post(
        f"/api/boards/{board_id}/assets",
        json={"asset_id": asset_id},
        headers=h_owner,
    )
    assert o_attach.status_code == 201

    # 5. Board viewer can now view and download the asset via board association!
    v_get = await async_client.get(f"/api/assets/{asset_id}", headers=h_viewer)
    assert v_get.status_code == 200
    assert "url" in v_get.json()

    # 6. Board viewer lists board assets
    b_assets = await async_client.get(f"/api/boards/{board_id}/assets", headers=h_viewer)
    assert b_assets.status_code == 200
    assert b_assets.json()["total"] == 1
    assert b_assets.json()["items"][0]["asset_id"] == asset_id

    # 7. Outsider is still denied (403)
    out_get = await async_client.get(f"/api/assets/{asset_id}", headers=h_outsider)
    assert out_get.status_code == 403


@pytest.mark.asyncio
async def test_gif_animation_flag_preservation(
    async_client: AsyncClient, mock_storage: MockStorageProvider
) -> None:
    """GIF uploads mark is_animated=True and support up to 15MB limit."""
    user, headers = await create_user_with_token(async_client, "Animator")

    # GIF within 15MB limit (e.g. 12 MB)
    res = await async_client.post(
        "/api/assets/upload-url",
        json={
            "filename": "dancing.gif",
            "content_type": "image/gif",
            "byte_size": 12 * 1024 * 1024,  # 12 MiB
            "media_type": "gif",
        },
        headers=headers,
    )
    assert res.status_code == 201
    aid = res.json()["asset_id"]
    key = res.json()["object_key"]

    mock_storage.set_mock_object(key, size=12 * 1024 * 1024, content_type="image/gif")
    comp_res = await async_client.post(f"/api/assets/{aid}/complete", json={}, headers=headers)
    assert comp_res.status_code == 200
    assert comp_res.json()["is_animated"] is True
    assert comp_res.json()["media_type"] == "gif"
