# System Architecture Baseline

This document summarizes the system architecture and component boundaries established across Phase 0 and Phase 1.

---

## High-Level Topology

```
                       +-----------------------------+
                       |       Client Browser        |
                       |  React + React-Konva + Yjs  |
                       +--------------+--------------+
                                      |
                      HTTP / REST     |      WSS / WebSocket
                      (FastAPI)       |      (Hocuspocus)
                                      |
               +----------------------+----------------------+
               |                                             |
               v                                             v
+-------------------------------+             +-------------------------------+
|       apps/api (FastAPI)      |             |  apps/collaboration (Node.js) |
| - Health/Readiness            |             | - Hocuspocus Server           |
| - Authentication & Sessions   |             | - Yjs Document Sync           |
| - Board CRUD & Permissions    |             | - Awareness / Cursors         |
| - R2 Asset Authorization      |             | - Persistence Provider        |
+---------------+---------------+             +---------------+---------------+
                |                                             |
                +----------------------+----------------------+
                                       |
                                       v
                        +------------------------------+
                        |     PostgreSQL (Database)    |
                        | - Users & Auth Identities    |
                        | - Boards & Memberships       |
                        | - Asset Metadata             |
                        | - Yjs Snapshots & Updates    |
                        +------------------------------+
```

---

## Phase 0 & Phase 1 Responsibilities

1. **Phase 0 (Repository & Environment)**
   - Pinned Python 3.13 and Node.js 22 runtimes.
   - Centralized `.env.example` with placeholders for all services.
   - Docker Compose baseline with healthchecked PostgreSQL 16 and Mailpit containers.
   - Monorepo folder layout separating presentation (`apps/web`), backend (`apps/api`), and real-time synchronization (`apps/collaboration`).

2. **Phase 1 (FastAPI API Foundation & HTTP Contracts)**
   - Pydantic Settings configuration with environment variable loading.
   - System probe endpoints (`/health`, `/ready`, `/api/version`).
   - Request ID tracing middleware (`X-Request-ID`).
   - Structured JSON request logging.
   - Uniform error envelope (`{"error": {"code": ..., "message": ..., "request_id": ...}}`).
   - Explicit CORS allowlist with credential support.
   - Modular API router skeleton with OpenAPI documentation.
