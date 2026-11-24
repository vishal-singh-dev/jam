# HTTP API Conventions and Standards

This document specifies HTTP API standards, status codes, request ID propagation, versioning, and error payloads for the Collaborative Whiteboard backend.

---

## 1. Request Identification & Tracing

- Every inbound HTTP request is tagged with a unique request ID.
- Clients may supply an existing request ID via the `X-Request-ID` header.
- If omitted or invalid, the API server generates a UUID v4 request ID.
- The request ID is:
  1. Stored in request state (`request.state.request_id`).
  2. Emitted in structured log lines for correlation.
  3. Returned in the HTTP response header `X-Request-ID`.
  4. Embedded in all error response payloads (`error.request_id`).

---

## 2. Status & System Endpoints

System probe endpoints are served without unnecessary routing prefixes to simplify container orchestrators and reverse proxies:

### `GET /health`
Liveness probe. Indicates whether the FastAPI application process is alive and responding.

- **Status Code**: `200 OK`
- **Response Shape**:
  ```json
  {
    "status": "healthy",
    "timestamp": "2026-11-15T10:00:00.000000Z"
  }
  ```

### `GET /ready`
Readiness probe. Indicates whether the application is configured and ready to accept traffic. In future phases, this will check downstream dependencies (PostgreSQL, Mailpit, R2 connectivity).

- **Status Code**: `200 OK`
- **Response Shape**:
  ```json
  {
    "status": "ready",
    "timestamp": "2026-11-15T10:00:00.000000Z",
    "checks": {
      "configuration": "ok"
    }
  }
  ```

### `GET /api/version`
Application version endpoint. Exposes semantic version, build environment, and active API contract version.

- **Status Code**: `200 OK`
- **Response Shape**:
  ```json
  {
    "version": "0.1.0",
    "environment": "development",
    "api_version": "v1"
  }
  ```

---

## 3. Standard Error Envelope

All API errors (4xx client errors and 5xx internal server errors) return a consistent JSON envelope:

```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human-readable description of what went wrong.",
    "details": [ ... ],
    "request_id": "c1f7a0b5-789a-4c21-9988-123456789abc"
  }
}
```

### Standard Error Codes
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request body, query parameters, or path parameters failed schema validation. `details` contains field-level errors. |
| `NOT_FOUND` | 404 | The requested route or entity does not exist. |
| `METHOD_NOT_ALLOWED` | 405 | HTTP method is not permitted on this path. |
| `UNAUTHORIZED` | 401 | Missing or invalid authentication credentials. |
| `FORBIDDEN` | 403 | Authenticated user lacks permission for the resource. |
| `CONFLICT` | 409 | Request conflicts with current database or entity state. |
| `INTERNAL_SERVER_ERROR` | 500 | Unhandled server error. Specific traceback details are masked in production. |

---

## 4. CORS Policy

- The API uses an explicit CORS allowlist configured via `CORS_ORIGINS`.
- Wildcard `*` origins are rejected when credentials (`allow_credentials=True`) are enabled.
- Permitted HTTP methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, `HEAD`.
- Permitted headers: `Authorization`, `Content-Type`, `X-Request-ID`, `Accept`, `Origin`.
- Exposed headers: `X-Request-ID`.

---

## 5. Modular Router Organization

All product feature endpoints are grouped into dedicated routers under `/api`:
- `/api/auth`: Authentication and session management (Phase 3).
- `/api/boards`: Board CRUD and metadata (Phase 4).
- `/api/boards/{board_id}/members`: Board membership and permissions (Phase 4).
- `/api/assets`: Cloudflare R2 presigned uploads and media management (Phase 5).
- `/api/boards/{board_id}/collaboration-token`: WebSocket collaboration tokens (Phase 7).
