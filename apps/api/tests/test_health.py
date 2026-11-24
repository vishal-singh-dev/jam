"""Tests for health and readiness diagnostic endpoints."""

from datetime import datetime

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_ok(async_client: AsyncClient) -> None:
    """GET /health must return HTTP 200 with healthy status and valid UTC timestamp."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

    # Verify timestamp is a valid ISO format datetime
    parsed_time = datetime.fromisoformat(data["timestamp"])
    assert parsed_time.tzinfo is not None or parsed_time.utcoffset() is not None


@pytest.mark.asyncio
async def test_readiness_check_returns_ready(async_client: AsyncClient) -> None:
    """GET /ready must return HTTP 200 with readiness status and subsystem checks."""
    response = await async_client.get("/ready")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ready"
    assert "timestamp" in data
    assert data.get("checks", {}).get("configuration") == "ok"
