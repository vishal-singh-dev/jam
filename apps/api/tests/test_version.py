"""Tests for version endpoint."""

import pytest
from httpx import AsyncClient

from src.config import Settings


@pytest.mark.asyncio
async def test_get_version_matches_settings(
    async_client: AsyncClient, test_settings: Settings
) -> None:
    """GET /api/version must return HTTP 200 with version, environment, and API version."""
    response = await async_client.get("/api/version")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == test_settings.api_version
    assert data["environment"] == test_settings.environment
    assert data["api_version"] == "v1"
