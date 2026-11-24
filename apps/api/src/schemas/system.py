"""Pydantic schemas for system and diagnostic endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response model."""

    status: str = Field(default="healthy", description="Application health status")
    timestamp: datetime = Field(description="UTC timestamp of the health check")


class ReadyResponse(BaseModel):
    """Readiness probe response model."""

    status: str = Field(default="ready", description="Application readiness status")
    timestamp: datetime = Field(description="UTC timestamp of the readiness check")
    checks: dict[str, str] = Field(
        default_factory=dict, description="Dictionary of subsystem check results"
    )


class VersionResponse(BaseModel):
    """Application version response model."""

    version: str = Field(description="Semantic version of the application")
    environment: str = Field(description="Current deployment environment")
    api_version: str = Field(default="v1", description="Current API contract version")
