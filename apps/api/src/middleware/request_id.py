"""Request ID tracking middleware."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.constants import HEADER_REQUEST_ID


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensure every HTTP request has an X-Request-ID and propagate it to the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound_request_id = request.headers.get(HEADER_REQUEST_ID)
        if inbound_request_id and inbound_request_id.strip():
            request_id = inbound_request_id.strip()
        else:
            request_id = str(uuid.uuid4())

        # Attach request_id to request.state for downstream access
        request.state.request_id = request_id

        # Process the request
        response = await call_next(request)

        # Ensure response contains the request ID header
        response.headers[HEADER_REQUEST_ID] = request_id
        return response
