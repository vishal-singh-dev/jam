"""FastAPI application entry point and factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import Settings, get_settings
from src.constants import API_V1_PREFIX, HEADER_REQUEST_ID
from src.errors.handlers import register_error_handlers
from src.middleware.logging import RequestLoggingMiddleware
from src.middleware.request_id import RequestIDMiddleware
from src.routers.assets import router as assets_router
from src.routers.auth import router as auth_router
from src.routers.boards import router as boards_router
from src.routers.collaboration import router as collaboration_router
from src.routers.members import router as members_router
from src.routers.system import router as system_router

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle events."""
    settings = getattr(app.state, "settings", None) or get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(
        "Starting Collaborative Whiteboard API (version=%s, env=%s)",
        settings.api_version,
        settings.environment,
    )
    yield
    logger.info("Shutting down Collaborative Whiteboard API")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure an instance of the FastAPI application."""
    active_settings = settings or get_settings()

    app = FastAPI(
        title="Collaborative Whiteboard API",
        description="REST and coordination API foundation for real-time collaborative whiteboard.",
        version=active_settings.api_version,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        debug=active_settings.debug,
        lifespan=lifespan,
    )

    # Store settings in application state and wire dependency override
    app.state.settings = active_settings
    app.dependency_overrides[get_settings] = lambda: active_settings

    # 1. CORS Middleware (must be outermost to handle preflight OPTIONS correctly)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["*"],
        expose_headers=[HEADER_REQUEST_ID],
    )

    # 2. Request Logging Middleware
    app.add_middleware(RequestLoggingMiddleware)

    # 3. Request ID Middleware
    app.add_middleware(RequestIDMiddleware)

    # 4. Standardized Global Error Handlers
    register_error_handlers(app)

    # 5. System Endpoints (/health, /ready, /api/version)
    app.include_router(system_router)

    # 6. Modular Product Routers under /api prefix
    api_v1_router = APIRouter(prefix=API_V1_PREFIX)
    api_v1_router.include_router(auth_router)
    api_v1_router.include_router(boards_router)
    api_v1_router.include_router(members_router)
    api_v1_router.include_router(assets_router)
    api_v1_router.include_router(collaboration_router)

    app.include_router(api_v1_router)

    return app


# Default application instance for ASGI servers (e.g. uvicorn src.main:app)
app = create_app()
