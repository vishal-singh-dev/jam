"""HTTP integration tests for Phase 3 authentication endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_signup_and_login_flow(async_client: AsyncClient) -> None:
    """Test full HTTP signup, login, cookie setting, and me retrieval."""
    email = f"api_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    # 1. Signup
    signup_res = await async_client.post(
        "/api/auth/signup",
        json={
            "display_name": "API Test User",
            "email": email,
            "password": password,
        },
    )
    assert signup_res.status_code == 201
    assert "Registration successful" in signup_res.json()["message"]

    # 2. Duplicate signup rejected
    dup_res = await async_client.post(
        "/api/auth/signup",
        json={
            "display_name": "Duplicate User",
            "email": email,
            "password": password,
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "CONFLICT"

    # 3. Login
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email
    assert "whiteboard_refresh" in login_res.cookies

    access_token = login_data["access_token"]

    # 4. Access /api/auth/me with Bearer token
    me_res = await async_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email


@pytest.mark.asyncio
async def test_api_login_invalid_credentials(async_client: AsyncClient) -> None:
    """Invalid credentials return 401 Unauthorized."""
    res = await async_client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_api_session_refresh_and_logout(async_client: AsyncClient) -> None:
    """Test session refresh with cookie rotation and logout session revocation."""
    email = f"refresh_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    # Signup and login
    await async_client.post(
        "/api/auth/signup",
        json={"display_name": "Refresh User", "email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    refresh_token = login_res.cookies.get("whiteboard_refresh")
    assert refresh_token is not None

    # Refresh session using cookie
    refresh_res = await async_client.post(
        "/api/auth/refresh",
        cookies={"whiteboard_refresh": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_token_data = refresh_res.json()
    assert "access_token" in new_token_data
    new_refresh_token = refresh_res.cookies.get("whiteboard_refresh")
    assert new_refresh_token is not None
    assert new_refresh_token != refresh_token

    # Logout
    logout_res = await async_client.post(
        "/api/auth/logout",
        cookies={"whiteboard_refresh": new_refresh_token},
    )
    assert logout_res.status_code == 200
    assert "Successfully logged out" in logout_res.json()["message"]


@pytest.mark.asyncio
async def test_api_google_login_endpoints(async_client: AsyncClient) -> None:
    """Google login generates auth URL and callback authenticates."""
    # 1. Initiate Google Login
    init_res = await async_client.get("/api/auth/google/login")
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert "accounts.google.com" in init_data["authorization_url"]
    assert "state" in init_data

    # 2. Callback
    code_val = f"oauth_code_{uuid.uuid4().hex[:8]}"
    state_val = init_data["state"]
    callback_res = await async_client.get(
        f"/api/auth/google/callback?code={code_val}&state={state_val}",
    )
    assert callback_res.status_code == 200
    cb_data = callback_res.json()
    assert "access_token" in cb_data
    assert cb_data["user"]["email_verified"] is True


@pytest.mark.asyncio
async def test_api_me_unauthenticated_rejected(async_client: AsyncClient) -> None:
    """Accessing /api/auth/me without credentials returns 401."""
    res = await async_client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_api_forgot_and_resend_verification_endpoints(async_client: AsyncClient) -> None:
    """Forgot password and resend verification return 200 without leaking account status."""
    res1 = await async_client.post(
        "/api/auth/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert res1.status_code == 200
    assert "password reset instructions" in res1.json()["message"].lower()

    res2 = await async_client.post(
        "/api/auth/resend-verification",
        json={"email": "nobody@example.com"},
    )
    assert res2.status_code == 200
    assert "verification link has been sent" in res2.json()["message"].lower()
