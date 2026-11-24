# Real-Time Collaborative Whiteboard

A production-grade, browser-based real-time collaborative whiteboard built with FastAPI, React (React-Konva), Yjs CRDT, Hocuspocus WebSocket collaboration service, PostgreSQL, and Cloudflare R2.

## Monorepo Structure

```
.
├── apps/
│   ├── api/             # FastAPI backend (REST API, auth, business logic, storage)
│   ├── web/             # React + Vite + TypeScript frontend canvas application
│   └── collaboration/   # Node.js + TypeScript Hocuspocus / Yjs collaboration service
├── infra/               # Infrastructure, Docker Compose, migrations
├── docs/                # Architecture, HTTP conventions, design specs
└── tests/
    └── e2e/             # Playwright end-to-end multi-client collaboration tests
```

## Prerequisites

- **Python**: 3.13 (`.python-version`)
- **Node.js**: LTS 20+ or 22+ (`.node-version`)
- **Docker & Docker Compose**: For local PostgreSQL and Mailpit services

## Quick Start

### 1. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Review and adjust any local variables if needed.

### 2. Infrastructure Services (PostgreSQL & Mailpit)

Start local PostgreSQL and Mailpit containers:

```bash
docker compose up -d
```

Verify service health:
- PostgreSQL: Port `5432`
- Mailpit Web UI: [http://localhost:8025](http://localhost:8025)
- Mailpit SMTP: Port `1025`

To stop infrastructure:

```bash
docker compose down
```

### 3. FastAPI Backend (`apps/api`)

#### Python Virtual Environment Setup

```bash
cd apps/api
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

#### Run Backend Development Server

From inside `apps/api`:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Or from the monorepo root:
```bash
uvicorn src.main:app --app-dir apps/api --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- Base API: [http://localhost:8000](http://localhost:8000)
- Health probe: [http://localhost:8000/health](http://localhost:8000/health)
- Readiness probe: [http://localhost:8000/ready](http://localhost:8000/ready)
- Version info: [http://localhost:8000/api/version](http://localhost:8000/api/version)
- Interactive OpenAPI Docs (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc Docs: [http://localhost:8000/redoc](http://localhost:8000/redoc)

#### Run Backend Tests

```bash
pytest
```

## HTTP API Conventions

For details on standard response structures, error handling, status codes, request ID tracing, and route conventions, refer to:
- [docs/api_conventions.md](docs/api_conventions.md)
- [docs/architecture.md](docs/architecture.md)
