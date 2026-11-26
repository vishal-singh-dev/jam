"""User entity model representing the core relational application identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.asset import Asset
    from src.models.auth import (
        AuthIdentity,
        EmailVerificationToken,
        PasswordResetToken,
        UserSession,
    )
    from src.models.board import Board, BoardMember


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User account model.

    The normalized_email field guarantees case-insensitive email uniqueness.
    External auth providers (Google, local) link to this user via AuthIdentity records.
    """

    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    identities: Mapped[list[AuthIdentity]] = relationship(
        "AuthIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    email_verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(
        "EmailVerificationToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Boards owned (RESTRICT on delete - user cannot be deleted while owning active boards)
    owned_boards: Mapped[list[Board]] = relationship(
        "Board",
        back_populates="owner",
        foreign_keys="Board.owner_id",
        passive_deletes=True,
    )

    # Board memberships
    board_memberships: Mapped[list[BoardMember]] = relationship(
        "BoardMember",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Assets owned
    assets: Mapped[list[Asset]] = relationship(
        "Asset",
        back_populates="owner",
        passive_deletes=True,
    )
