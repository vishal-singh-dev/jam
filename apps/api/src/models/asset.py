"""Asset metadata and board-asset association models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from src.models.board import Board
    from src.models.user import User


class Asset(Base, UUIDPrimaryKeyMixin):
    """Uploaded media asset metadata (images, stickers, GIFs, backgrounds).

    Binary payloads are stored in Cloudflare R2; PostgreSQL stores metadata, dimensions,
    and server-controlled object keys.
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint(
            "storage_provider",
            "bucket_name",
            "object_key",
            name="uq_assets_storage_bucket_key",
        ),
        CheckConstraint(
            "media_type IN ('image', 'gif', 'sticker', 'background')",
            name="chk_assets_media_type",
        ),
        CheckConstraint("byte_size > 0", name="chk_assets_byte_size"),
        CheckConstraint("width IS NULL OR width > 0", name="chk_assets_width"),
        CheckConstraint("height IS NULL OR height > 0", name="chk_assets_height"),
        Index("ix_assets_owner_id", "owner_id"),
        Index("ix_assets_media_type", "media_type"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    storage_provider: Mapped[str] = mapped_column(
        String(30),
        default="cloudflare_r2",
        nullable=False,
    )
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_animated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    owner: Mapped[User] = relationship("User", back_populates="assets")
    board_associations: Mapped[list[BoardAsset]] = relationship(
        "BoardAsset",
        back_populates="asset",
        passive_deletes=True,
    )


class BoardAsset(Base, UUIDPrimaryKeyMixin):
    """Explicit association between a board and an asset authorized for use on that canvas."""

    __tablename__ = "board_assets"
    __table_args__ = (
        UniqueConstraint("board_id", "asset_id", name="uq_board_assets_board_asset"),
        Index("ix_board_assets_board_id", "board_id"),
        Index("ix_board_assets_asset_id", "asset_id"),
    )

    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    board: Mapped[Board] = relationship("Board", back_populates="board_assets")
    asset: Mapped[Asset] = relationship("Asset", back_populates="board_associations")
    added_by: Mapped[User] = relationship("User", foreign_keys=[added_by_user_id])
