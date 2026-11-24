"""System and health check endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.config import Settings, get_settings
from src.schemas.system import HealthResponse, ReadyResponse, VersionResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application liveness probe",
    description="Returns HTTP 200 if the FastAPI application process is up and running.",
)
async def health_check() -> HealthResponse:
    """Return health liveness status with current UTC timestamp."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    summary="Application readiness probe",
    description=(
        "Returns HTTP 200 if the application and required dependencies are ready to serve traffic."
    ),
)
async def readiness_check() -> ReadyResponse:
    """Return readiness status indicating application configuration is valid."""
    # In Phase 1, configuration and server readiness are verified.
    # Future phases will add PostgreSQL and Mailpit checks here.
    return ReadyResponse(
        status="ready",
        timestamp=datetime.now(UTC),
        checks={
            "configuration": "ok",
        },
    )


@router.get(
    "/api/version",
    response_model=VersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Application version information",
    description="Returns current application version and deployment environment.",
)
async def get_version(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionResponse:
    """Return application version, environment, and API contract version."""
    return VersionResponse(
        version=settings.api_version,
        environment=settings.environment,
        api_version="v1",
    )
