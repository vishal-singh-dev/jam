"""Tests for uniform error responses on client and server errors."""

import pytest
from httpx import AsyncClient

from src.constants import (
    ERROR_CODE_INTERNAL,
    ERROR_CODE_METHOD_NOT_ALLOWED,
    ERROR_CODE_NOT_FOUND,
    ERROR_CODE_VALIDATION,
    HEADER_REQUEST_ID,
)


@pytest.mark.asyncio
async def test_404_not_found_error_envelope(async_client: AsyncClient) -> None:
    """Non-existent endpoints must return HTTP 404 with standardized error envelope."""
    response = await async_client.get("/non-existent-route")
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == ERROR_CODE_NOT_FOUND
    assert "message" in error
    assert "request_id" in error
    assert error["request_id"] == response.headers.get(HEADER_REQUEST_ID)


@pytest.mark.asyncio
async def test_405_method_not_allowed_error_envelope(async_client: AsyncClient) -> None:
    """Invoking an invalid HTTP method must return 405 with standardized error envelope."""
    response = await async_client.post("/health")
    assert response.status_code == 405

    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == ERROR_CODE_METHOD_NOT_ALLOWED
    assert "request_id" in error
    assert error["request_id"] == response.headers.get(HEADER_REQUEST_ID)


@pytest.mark.asyncio
async def test_422_validation_error_envelope(async_client: AsyncClient) -> None:
    """Schema validation failure must return HTTP 422 with structured details and request_id."""
    invalid_payload = {"title": "a", "count": -5}
    response = await async_client.post("/api/test-probes/validation", json=invalid_payload)
    assert response.status_code == 422

    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == ERROR_CODE_VALIDATION
    assert isinstance(error.get("details"), list)
    assert len(error["details"]) > 0
    assert "request_id" in error
    assert error["request_id"] == response.headers.get(HEADER_REQUEST_ID)


@pytest.mark.asyncio
async def test_500_server_error_envelope(async_client: AsyncClient) -> None:
    """Unhandled server errors must return HTTP 500 with standardized error envelope."""
    response = await async_client.get("/api/test-probes/server-error")
    assert response.status_code == 500

    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == ERROR_CODE_INTERNAL
    assert "request_id" in error
    assert error["request_id"] == response.headers.get(HEADER_REQUEST_ID)
