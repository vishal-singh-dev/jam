"""Board domain models: boards, members, documents, updates, and invitations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.authorization.roles import BoardRole
from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from src.models.asset import BoardAsset
    from src.models.user import User


class Board(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Board entity representing a collaborative whiteboard canvas."""

    __tablename__ = "boards"
    __table_args__ = (Index("ix_boards_owner_deleted", "owner_id", "deleted_at"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Relationships
    owner: Mapped[User] = relationship(
        "User",
        back_populates="owned_boards",
        foreign_keys=[owner_id],
    )
    members: Mapped[list[BoardMember]] = relationship(
        "BoardMember",
        back_populates="board",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    document: Mapped[BoardDocument | None] = relationship(
        "BoardDocument",
        back_populates="board",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    updates: Mapped[list[BoardUpdate]] = relationship(
        "BoardUpdate",
        back_populates="board",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BoardUpdate.sequence",
    )
    board_assets: Mapped[list[BoardAsset]] = relationship(
        "BoardAsset",
        back_populates="board",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    invitations: Mapped[list[BoardInvitation]] = relationship(
        "BoardInvitation",
        back_populates="board",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BoardMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Explicit membership and authorization role on a specific board."""

    __tablename__ = "board_members"
    __table_args__ = (
        UniqueConstraint("board_id", "user_id", name="uq_board_members_board_user"),
        CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="chk_board_members_role",
        ),
        Index("ix_board_members_user_board", "user_id", "board_id"),
        Index("ix_board_members_board_role", "board_id", "role"),
    )

    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=BoardRole.VIEWER.value,
        nullable=False,
    )

    board: Mapped[Board] = relationship("Board", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="board_memberships")


class BoardDocument(Base):
    """Authoritative compressed Yjs document state snapshot for a board."""

    __tablename__ = "board_documents"

    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    snapshot_state_vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    snapshot_version: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    board: Mapped[Board] = relationship("Board", back_populates="document")


class BoardUpdate(Base):
    """Append-only incremental Yjs binary updates following the current snapshot."""

    __tablename__ = "board_updates"
    __table_args__ = (
        UniqueConstraint("board_id", "sequence", name="uq_board_updates_board_sequence"),
        Index("ix_board_updates_board_sequence", "board_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    board: Mapped[Board] = relationship("Board", back_populates="updates")


class BoardInvitation(Base, UUIDPrimaryKeyMixin):
    """Pending email-based invitation to join a board with a designated role."""

    __tablename__ = "board_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('editor', 'viewer')",
            name="chk_board_invitations_role",
        ),
        Index("ix_board_invitations_board_email", "board_id", "invited_email_normalized"),
    )

    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_email_normalized: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        index=True,
        nullable=False,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    board: Mapped[Board] = relationship("Board", back_populates="invitations")
    invited_by: Mapped[User] = relationship("User", foreign_keys=[invited_by_user_id])
