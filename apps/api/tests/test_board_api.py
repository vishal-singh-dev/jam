"""End-to-end HTTP integration tests for Phase 4 board and membership APIs."""

import uuid

import pytest
from httpx import AsyncClient


async def create_user_with_token(
    client: AsyncClient, name: str = "Test User"
) -> tuple[dict, dict[str, str]]:
    """Helper to register and authenticate a user, returning user payload and auth headers."""
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


@pytest.mark.asyncio
async def test_create_board_atomic_owner(async_client: AsyncClient) -> None:
    """Creating a board atomically sets the owner and owner membership row."""
    user, headers = await create_user_with_token(async_client, "Owner User")

    res = await async_client.post(
        "/api/boards",
        json={"title": "Sprint Planning Whiteboard"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Sprint Planning Whiteboard"
    assert data["owner_id"] == user["id"]
    assert data["current_user_role"] == "owner"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_boards_pagination_and_membership_isolation(
    async_client: AsyncClient,
) -> None:
    """Users only list boards they are members of, with correct pagination metadata."""
    user1, h1 = await create_user_with_token(async_client, "User 1")
    user2, h2 = await create_user_with_token(async_client, "User 2")

    # User 1 creates 3 boards
    await async_client.post("/api/boards", json={"title": "Board 1"}, headers=h1)
    await async_client.post("/api/boards", json={"title": "Board 2"}, headers=h1)
    await async_client.post("/api/boards", json={"title": "Board 3"}, headers=h1)

    # User 2 creates 1 board
    await async_client.post("/api/boards", json={"title": "User 2 Board"}, headers=h2)

    # User 1 lists boards with page_size=2
    list_res = await async_client.get("/api/boards?page=1&page_size=2", headers=h1)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] == 3
    assert len(list_data["items"]) == 2
    assert list_data["page"] == 1
    assert list_data["page_size"] == 2

    # User 2 sees only their 1 board
    list2_res = await async_client.get("/api/boards", headers=h2)
    assert list2_res.status_code == 200
    assert list2_res.json()["total"] == 1
    assert list2_res.json()["items"][0]["title"] == "User 2 Board"


@pytest.mark.asyncio
async def test_get_board_permissions(async_client: AsyncClient) -> None:
    """Owner, editor, and viewer can view board metadata; non-members are denied."""
    owner, h_owner = await create_user_with_token(async_client, "Owner")
    editor, h_editor = await create_user_with_token(async_client, "Editor")
    viewer, h_viewer = await create_user_with_token(async_client, "Viewer")
    outsider, h_outsider = await create_user_with_token(async_client, "Outsider")

    # Create board
    b_res = await async_client.post("/api/boards", json={"title": "Team Board"}, headers=h_owner)
    board_id = b_res.json()["id"]

    # Add editor and viewer
    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": editor["id"], "role": "editor"},
        headers=h_owner,
    )
    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": viewer["id"], "role": "viewer"},
        headers=h_owner,
    )

    # 1. Owner GET
    r_owner = await async_client.get(f"/api/boards/{board_id}", headers=h_owner)
    assert r_owner.status_code == 200
    assert r_owner.json()["current_user_role"] == "owner"

    # 2. Editor GET
    r_editor = await async_client.get(f"/api/boards/{board_id}", headers=h_editor)
    assert r_editor.status_code == 200
    assert r_editor.json()["current_user_role"] == "editor"

    # 3. Viewer GET
    r_viewer = await async_client.get(f"/api/boards/{board_id}", headers=h_viewer)
    assert r_viewer.status_code == 200
    assert r_viewer.json()["current_user_role"] == "viewer"

    # 4. Outsider GET
    r_outsider = await async_client.get(f"/api/boards/{board_id}", headers=h_outsider)
    assert r_outsider.status_code == 403
    assert r_outsider.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_update_and_delete_board_permissions(async_client: AsyncClient) -> None:
    """Only owners can update metadata or soft-delete boards."""
    owner, h_owner = await create_user_with_token(async_client, "Board Owner")
    editor, h_editor = await create_user_with_token(async_client, "Board Editor")

    b_res = await async_client.post(
        "/api/boards", json={"title": "Original Title"}, headers=h_owner
    )
    board_id = b_res.json()["id"]

    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": editor["id"], "role": "editor"},
        headers=h_owner,
    )

    # 1. Editor cannot update title (403)
    e_update = await async_client.patch(
        f"/api/boards/{board_id}",
        json={"title": "Editor Hacked Title"},
        headers=h_editor,
    )
    assert e_update.status_code == 403

    # 2. Owner updates title (200)
    o_update = await async_client.patch(
        f"/api/boards/{board_id}",
        json={"title": "Updated Title by Owner"},
        headers=h_owner,
    )
    assert o_update.status_code == 200
    assert o_update.json()["title"] == "Updated Title by Owner"

    # 3. Editor cannot delete board (403)
    e_del = await async_client.delete(f"/api/boards/{board_id}", headers=h_editor)
    assert e_del.status_code == 403

    # 4. Owner soft-deletes board (200)
    o_del = await async_client.delete(f"/api/boards/{board_id}", headers=h_owner)
    assert o_del.status_code == 200

    # 5. Subsequent GET returns 404
    get_res = await async_client.get(f"/api/boards/{board_id}", headers=h_owner)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_member_crud_and_duplicates(async_client: AsyncClient) -> None:
    """Owner manages members, rejects duplicate additions, editors cannot manage members."""
    owner, h_owner = await create_user_with_token(async_client, "Owner")
    member1, h_m1 = await create_user_with_token(async_client, "Member 1")
    member2, _ = await create_user_with_token(async_client, "Member 2")

    b_res = await async_client.post(
        "/api/boards", json={"title": "Membership Board"}, headers=h_owner
    )
    board_id = b_res.json()["id"]

    # 1. Add member by user_id
    add_res = await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": member1["id"], "role": "editor"},
        headers=h_owner,
    )
    assert add_res.status_code == 201
    assert add_res.json()["role"] == "editor"

    # 2. Add member by email
    add2_res = await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"email": member2["email"], "role": "viewer"},
        headers=h_owner,
    )
    assert add2_res.status_code == 201
    assert add2_res.json()["role"] == "viewer"

    # 3. Duplicate addition rejected with 409
    dup_res = await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": member1["id"], "role": "viewer"},
        headers=h_owner,
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "CONFLICT"

    # 4. Editor cannot add members
    e_add = await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"email": "random@example.com", "role": "viewer"},
        headers=h_m1,
    )
    assert e_add.status_code == 403

    # 5. Update role: promote viewer to editor
    patch_res = await async_client.patch(
        f"/api/boards/{board_id}/members/{member2['id']}",
        json={"role": "editor"},
        headers=h_owner,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["role"] == "editor"

    # 6. List members (3 total: owner, member1, member2)
    list_res = await async_client.get(f"/api/boards/{board_id}/members", headers=h_owner)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 3


@pytest.mark.asyncio
async def test_last_owner_protection_and_self_removal(async_client: AsyncClient) -> None:
    """Sole owner cannot be removed or demoted; non-owner members can leave the board."""
    owner, h_owner = await create_user_with_token(async_client, "Sole Owner")
    editor, h_editor = await create_user_with_token(async_client, "Regular Editor")

    b_res = await async_client.post(
        "/api/boards", json={"title": "Protection Board"}, headers=h_owner
    )
    board_id = b_res.json()["id"]

    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": editor["id"], "role": "editor"},
        headers=h_owner,
    )

    # 1. Owner attempts to demote self -> 409 Conflict (LastOwnerProtectionError)
    demote_res = await async_client.patch(
        f"/api/boards/{board_id}/members/{owner['id']}",
        json={"role": "editor"},
        headers=h_owner,
    )
    assert demote_res.status_code == 409
    assert "last owner" in demote_res.json()["error"]["message"].lower()

    # 2. Owner attempts to remove self -> 409 Conflict
    remove_self_res = await async_client.delete(
        f"/api/boards/{board_id}/members/{owner['id']}",
        headers=h_owner,
    )
    assert remove_self_res.status_code == 409

    # 3. Editor leaves the board (self-removal) -> 200 OK
    leave_res = await async_client.delete(
        f"/api/boards/{board_id}/members/{editor['id']}",
        headers=h_editor,
    )
    assert leave_res.status_code == 200

    # 4. Verify editor is no longer a member
    get_res = await async_client.get(f"/api/boards/{board_id}", headers=h_editor)
    assert get_res.status_code == 403


@pytest.mark.asyncio
async def test_atomic_ownership_transfer(async_client: AsyncClient) -> None:
    """Ownership transfer updates boards.owner_id, promotes target, and demotes previous owner."""
    old_owner, h_old = await create_user_with_token(async_client, "Old Owner")
    new_owner, h_new = await create_user_with_token(async_client, "New Owner")

    b_res = await async_client.post(
        "/api/boards", json={"title": "Ownership Transfer Board"}, headers=h_old
    )
    board_id = b_res.json()["id"]

    # Add new_owner as editor initially
    await async_client.post(
        f"/api/boards/{board_id}/members",
        json={"user_id": new_owner["id"], "role": "editor"},
        headers=h_old,
    )

    # Transfer ownership
    transfer_res = await async_client.post(
        f"/api/boards/{board_id}/transfer-ownership",
        json={"new_owner_id": new_owner["id"]},
        headers=h_old,
    )
    assert transfer_res.status_code == 200
    assert transfer_res.json()["owner_id"] == new_owner["id"]

    # Verify old owner is now demoted to editor (cannot delete board)
    del_res = await async_client.delete(f"/api/boards/{board_id}", headers=h_old)
    assert del_res.status_code == 403

    # Verify new owner is now owner (can update board title)
    update_res = await async_client.patch(
        f"/api/boards/{board_id}",
        json={"title": "Title By New Owner"},
        headers=h_new,
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Title By New Owner"
    assert update_res.json()["current_user_role"] == "owner"
