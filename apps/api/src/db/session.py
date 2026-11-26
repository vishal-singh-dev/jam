"""Database engine and asynchronous session factory management."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Create and cache the async SQLAlchemy engine."""
    url = database_url or get_settings().database_url
    if not url:
        raise ValueError("DATABASE_URL is not configured in settings or environment.")

    # Normalize url driver scheme if needed
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    is_testing = get_settings().environment == "testing"
    if is_testing:
        return create_async_engine(
            url,
            echo=get_settings().debug,
            poolclass=NullPool,
        )

    return create_async_engine(
        url,
        echo=get_settings().debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    """Create an async sessionmaker bound to the given or default engine."""
    eng = engine or get_engine()
    return async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async database session wrapped in a transaction context."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
