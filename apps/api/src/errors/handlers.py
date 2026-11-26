"""Global exception handlers providing uniform error envelopes."""

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.authorization.exceptions import (
    AuthorizationError,
    InvalidRoleError,
    LastOwnerProtectionError,
)
from src.constants import (
    ERROR_CODE_BAD_REQUEST,
    ERROR_CODE_CONFLICT,
    ERROR_CODE_FORBIDDEN,
    ERROR_CODE_INTERNAL,
    ERROR_CODE_METHOD_NOT_ALLOWED,
    ERROR_CODE_NOT_FOUND,
    ERROR_CODE_UNAUTHORIZED,
    ERROR_CODE_VALIDATION,
    HEADER_REQUEST_ID,
)
from src.schemas.errors import ErrorEnvelope, ErrorResponse

logger = logging.getLogger("api.errors")

HTTP_422_CODE = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)

HTTP_STATUS_CODE_MAP = {
    status.HTTP_400_BAD_REQUEST: ERROR_CODE_BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ERROR_CODE_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ERROR_CODE_FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ERROR_CODE_NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ERROR_CODE_METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ERROR_CODE_CONFLICT,
    HTTP_422_CODE: ERROR_CODE_VALIDATION,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ERROR_CODE_INTERNAL,
}


def _get_request_id(request: Request) -> str:
    """Retrieve existing request ID from state or generate a fallback."""
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = request.headers.get(HEADER_REQUEST_ID)
    if not request_id:
        request_id = str(uuid.uuid4())
    return str(request_id)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions."""
    request_id = _get_request_id(request)
    code = HTTP_STATUS_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = str(exc.detail) if exc.detail else "An HTTP error occurred"

    error_payload = ErrorResponse(
        error=ErrorEnvelope(
            code=code,
            message=message,
            details=None,
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload.model_dump(),
        headers={HEADER_REQUEST_ID: request_id},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors with formatted details."""
    request_id = _get_request_id(request)
    details = exc.errors()

    error_payload = ErrorResponse(
        error=ErrorEnvelope(
            code=ERROR_CODE_VALIDATION,
            message="Request validation failed. Check request body, query parameters, or headers.",
            details=details,
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=HTTP_422_CODE,
        content=error_payload.model_dump(),
        headers={HEADER_REQUEST_ID: request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server exceptions."""
    request_id = _get_request_id(request)
    logger.exception("Unhandled server exception: %s (request_id=%s)", exc, request_id)

    error_payload = ErrorResponse(
        error=ErrorEnvelope(
            code=ERROR_CODE_INTERNAL,
            message="An unexpected server error occurred. Please try again later.",
            details=None,
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump(),
        headers={HEADER_REQUEST_ID: request_id},
    )


async def authorization_exception_handler(
    request: Request, exc: AuthorizationError
) -> JSONResponse:
    """Handle domain authorization exceptions."""
    request_id = _get_request_id(request)
    status_code = status.HTTP_403_FORBIDDEN
    error_code = ERROR_CODE_FORBIDDEN

    if isinstance(exc, LastOwnerProtectionError):
        status_code = status.HTTP_409_CONFLICT
        error_code = ERROR_CODE_CONFLICT
    elif isinstance(exc, InvalidRoleError):
        status_code = status.HTTP_400_BAD_REQUEST
        error_code = ERROR_CODE_BAD_REQUEST

    error_payload = ErrorResponse(
        error=ErrorEnvelope(
            code=error_code,
            message=str(exc),
            details=None,
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=error_payload.model_dump(),
        headers={HEADER_REQUEST_ID: request_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all global error handlers on the FastAPI application."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(AuthorizationError, authorization_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
