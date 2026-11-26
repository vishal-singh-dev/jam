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

3. **Phase 2 (PostgreSQL Models, Migrations, Referential Integrity & Decoupled Authorization)**
   - **Dedicated Authorization Module (`src/authorization`)**: Decoupled from application routers and generic models. Defines `BoardRole`, `BoardPermission`, `ROLE_PERMISSIONS` matrix, policy evaluation (`has_board_permission`, `can_mutate_canvas_content`), and invariant enforcement (`validate_owner_count_invariant`, `LastOwnerProtectionError`).
   - **SQLAlchemy 2.0 Async Base & Models (`src/models`)**:
     - `users`: Core relational user identity with unique `normalized_email`.
     - `auth_identities`: Local and Google identities with check constraints and partial unique indexes (one local identity per user).
     - `user_sessions`: Rotating refresh token storage with expiration and revocation indexes.
     - `email_verification_tokens` & `password_reset_tokens`: Single-use expiring token hashes.
     - `boards`: Board entity with soft delete support and owner reference (`ON DELETE RESTRICT`).
     - `board_members`: Board membership and role assignments (`owner`, `editor`, `viewer`) with `(board_id, user_id)` uniqueness.
     - `board_documents` & `board_updates`: Durable binary Yjs snapshots and sequence-ordered append updates.
     - `assets` & `board_assets`: Cloudflare R2 metadata and explicit board-asset associations with delete restrictions.
     - `board_invitations`: Role-scoped pending invitations with expiration.
   - **Transactional Invariants (`src/db/invariants.py`)**: Atomic creation of board + owner membership, transactional ownership transfer, and last-owner protection.
   - **Alembic Async Migrations (`alembic/`)**: Initial migration `36f5337861bd` managing full relational schema, indexes, and constraints with asyncpg.

4. **Phase 3 (Authentication and Session Lifecycle)**
   - **Cryptographic Services (`src/auth/crypto.py`)**:
     - Password hashing via Argon2id with memory/time cost parameters.
     - Persistent token hashing via SHA-256 (only token hashes stored in database).
     - Short-lived JWT access tokens (15-minute expiration, HS256, strictly validated claims).
     - Case-insensitive, stripped email normalization (`normalized_email`).
   - **Google OIDC Flow (`src/auth/oidc.py`)**:
     - Authorization code flow with PKCE (`S256`), secure random `state` and `nonce`.
     - ID token verification (issuer, audience, expiry, nonce, verified email).
     - Strict no-auto-linking policy: Google identities link to accounts by `sub`; attempting to sign in with an email that already exists as a local password account is rejected.
   - **Mailpit SMTP Delivery (`src/auth/email.py`)**:
     - Transactional verification and password reset emails sent via Mailpit SMTP (`localhost:1025`).
   - **Session & Token Management (`src/auth/service.py`)**:
     - Rotating refresh token sessions (`user_sessions`) with lineage tracking.
     - Automatic token reuse detection (revoking downstream sessions if a revoked token is re-submitted).
     - Single-use, expiring email verification and password reset tokens.
     - Comprehensive session revocation upon password reset.
     - Anti-enumeration behavior on login, resend verification, and forgot password endpoints.
   - **Authentication Dependencies (`src/auth/dependencies.py`)**:
     - `get_current_user`: Validates JWT bearer token and active user status.
     - `get_current_verified_user`: Enforces `email_verified=True`.
     - `get_optional_current_user`: Permissive authentication for optional context.
   - **API Endpoints (`src/routers/auth.py`)**:
     - `/api/auth/signup`, `/api/auth/login`, `/api/auth/google/login`, `/api/auth/google/callback`, `/api/auth/verify-email`, `/api/auth/resend-verification`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/forgot-password`, `/api/auth/reset-password`, `/api/auth/me`.
     - Secure, HTTP-only, SameSite session cookies (`whiteboard_refresh`, `whiteboard_csrf`).

5. **Phase 4 (Board CRUD, Membership, and Permissions)**
   - **Decoupled Authorization Dependencies (`src/authorization/dependencies.py`)**:
     - `get_board_membership`: Resolves and validates board existence, soft-delete state (`deleted_at is None`), and active membership for the authenticated user.
     - `require_board_permission_dep(permission)`: Enforces server-side permissions (`READ_BOARD`, `UPDATE_METADATA`, `DELETE_BOARD`, `MANAGE_MEMBERS`, `TRANSFER_OWNERSHIP`) based on the caller's board role.
   - **Domain Invariants & Protections**:
     - Atomic board creation with initial owner membership (`create_board_with_owner_tx`).
     - Atomic board ownership transfer (`transfer_board_ownership_tx`), promoting the new owner and demoting the previous owner to editor.
     - Last-owner protection (`validate_owner_count_invariant` / `LastOwnerProtectionError` -> 409 Conflict): Prevents demoting or removing the sole owner of a board.
     - Member self-removal (leaving the board) without requiring owner permission.
     - Soft deletion: Boards are marked with `deleted_at = UTC` and automatically filtered out from user listings and detail views.
   - **API Endpoints**:
     - `POST /api/boards`: Create whiteboard canvas with atomic owner membership.
     - `GET /api/boards`: Paginated listing of boards for the current user, returning total count and user role.
     - `GET /api/boards/{board_id}`: Fetch board metadata (owner, editor, viewer).
     - `PATCH /api/boards/{board_id}`: Update title (owner only).
     - `DELETE /api/boards/{board_id}`: Soft-delete board (owner only).
     - `POST /api/boards/{board_id}/transfer-ownership`: Transfer ownership atomically (owner only).
     - `GET /api/boards/{board_id}/members`: List all board members with roles and user details.
     - `POST /api/boards/{board_id}/members`: Add new editor/viewer by user ID or email (owner only; rejects duplicate memberships).
     - `PATCH /api/boards/{board_id}/members/{user_id}`: Update member role (owner only).
     - `DELETE /api/boards/{board_id}/members/{user_id}`: Remove member (owner or member self-removal).
