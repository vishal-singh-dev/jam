"""Tests for request ID middleware and header propagation."""

import uuid

import pytest
from httpx import AsyncClient

from src.constants import HEADER_REQUEST_ID


@pytest.mark.asyncio
async def test_request_id_generated_automatically(async_client: AsyncClient) -> None:
    """When client provides no X-Request-ID, the server generates a valid UUID."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    request_id = response.headers.get(HEADER_REQUEST_ID)
    assert request_id is not None
    assert len(request_id) > 0

    # Validate that it is a parseable UUID
    parsed_uuid = uuid.UUID(request_id)
    assert str(parsed_uuid) == request_id


@pytest.mark.asyncio
async def test_request_id_preserved_when_supplied_by_client(async_client: AsyncClient) -> None:
    """When client supplies X-Request-ID, the server echoes and propagates it."""
    custom_request_id = "custom-trace-uuid-12345-abcdef"
    response = await async_client.get(
        "/health",
        headers={HEADER_REQUEST_ID: custom_request_id},
    )
    assert response.status_code == 200
    assert response.headers.get(HEADER_REQUEST_ID) == custom_request_id
