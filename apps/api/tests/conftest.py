"""Pytest configuration and shared fixtures."""

from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config import Settings
from src.db.session import get_db
from src.main import create_app


class SampleValidationBody(BaseModel):
    """Schema used to test 422 RequestValidationError handling."""

    title: str = Field(min_length=3, max_length=50)
    count: int = Field(gt=0)


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated application settings for testing."""
    return Settings(
        environment="testing",
        api_version="0.1.0-test",
        cors_origins=["http://localhost:5173", "http://testserver"],
        secret_key="test-secret-key-for-unit-and-integration-tests",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/whiteboard_db",
        debug=False,
    )


@pytest.fixture
def test_app(test_settings: Settings) -> FastAPI:
    """Create a test FastAPI instance with helper test endpoints for error testing."""
    app = create_app(settings=test_settings)

    test_engine = create_async_engine(test_settings.database_url, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Attach a test-only router to verify 422 and 500 error envelopes
    test_router = APIRouter(prefix="/api/test-probes", tags=["Test Probes"])

    @test_router.post("/validation")
    async def probe_validation(body: SampleValidationBody) -> dict[str, str]:
        return {"status": "ok", "title": body.title}

    @test_router.get("/server-error")
    async def probe_server_error() -> None:
        raise RuntimeError("Simulated internal server fault for test verification")

    app.include_router(test_router)
    return app


@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Provide an HTTPX AsyncClient bound to the test application."""
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
