"""Tests for explicit CORS configuration and preflight handling."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_allowed_origin(async_client: AsyncClient) -> None:
    """Allowed origin must receive Access-Control-Allow-Origin and credentials headers."""
    response = await async_client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "x-request-id" in response.headers.get("access-control-expose-headers", "").lower()


@pytest.mark.asyncio
async def test_cors_disallowed_origin(async_client: AsyncClient) -> None:
    """Disallowed origin must NOT receive Access-Control-Allow-Origin header."""
    response = await async_client.get(
        "/health",
        headers={"Origin": "http://untrusted-external-site.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_cors_preflight_options_request(async_client: AsyncClient) -> None:
    """CORS preflight OPTIONS request from allowed origin must succeed with allow methods."""
    response = await async_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "GET" in response.headers.get("access-control-allow-methods", "")
