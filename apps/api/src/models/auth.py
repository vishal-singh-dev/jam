"""Authentication, session, and verification token models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from src.models.user import User


class AuthIdentity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """External or local identity attached to a user.

    Supports 'local' (Argon2id password hash) and 'google' (OIDC sub).
    """

    __tablename__ = "auth_identities"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('local', 'google')",
            name="chk_auth_identities_provider",
        ),
        CheckConstraint(
            "((provider = 'local' AND password_hash IS NOT NULL) OR "
            "(provider = 'google' AND provider_subject IS NOT NULL))",
            name="chk_auth_identities_credentials",
        ),
        Index(
            "uq_auth_identities_provider_subject",
            "provider",
            "provider_subject",
            unique=True,
            postgresql_where=text("provider_subject IS NOT NULL"),
        ),
        Index(
            "uq_auth_identities_user_local",
            "user_id",
            unique=True,
            postgresql_where=text("provider = 'local'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="identities")


class UserSession(Base, UUIDPrimaryKeyMixin):
    """Application session backing rotating refresh tokens."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_revoked", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    replaced_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")
    replaced_by: Mapped[UserSession | None] = relationship(
        "UserSession",
        remote_side="UserSession.id",
        foreign_keys=[replaced_by_session_id],
    )


class EmailVerificationToken(Base, UUIDPrimaryKeyMixin):
    """Single-use email verification token."""

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="email_verification_tokens")


class PasswordResetToken(Base, UUIDPrimaryKeyMixin):
    """Single-use password reset token."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="password_reset_tokens")
