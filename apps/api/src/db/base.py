"""SQLAlchemy DeclarativeBase and reusable model mixins."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy relational models."""

    def __repr__(self) -> str:
        """Provide a clean string representation for models."""
        attrs = [f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_")]
        return f"{self.__class__.__name__}({', '.join(attrs)})"

    def to_dict(self) -> dict[str, Any]:
        """Convert model attributes to a standard dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class UUIDPrimaryKeyMixin:
    """Mixin providing a UUID primary key for externally referenced entities."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin:
    """Mixin providing standardized timezone-aware UTC created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
