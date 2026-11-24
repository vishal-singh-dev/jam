"""Pydantic schemas for standardized error envelopes."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Inner error payload containing error code, message, optional details, and request ID."""

    code: str = Field(description="Machine-readable error classification code")
    message: str = Field(description="Human-readable explanation of the error")
    details: list[Any] | None = Field(
        default=None, description="Optional structured details such as validation issues"
    )
    request_id: str | None = Field(
        default=None, description="Request ID associated with the failed operation"
    )


class ErrorResponse(BaseModel):
    """Standardized top-level API error envelope."""

    error: ErrorEnvelope
