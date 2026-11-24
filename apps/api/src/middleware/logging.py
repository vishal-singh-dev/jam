"""Structured request logging middleware."""

import json
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log structured information about incoming HTTP requests and outgoing responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        response: Response | None = None
        error_occurred = False

        try:
            response = await call_next(request)
            return response
        except Exception:
            error_occurred = True
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            request_id = getattr(request.state, "request_id", None)
            client_ip = request.client.host if request.client else "unknown"
            status_code = response.status_code if response else (500 if error_occurred else 0)

            log_data = {
                "request_id": request_id,
                "client_ip": client_ip,
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }

            if status_code >= 500 or error_occurred:
                logger.error(json.dumps(log_data))
            elif status_code >= 400:
                logger.warning(json.dumps(log_data))
            else:
                logger.info(json.dumps(log_data))
