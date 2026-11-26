"""Cryptographic utilities: Argon2id password hashing, token hashing, and JWT tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from src.config import Settings, get_settings

# Argon2id password hasher with recommended default parameters
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    """Normalize email address to lowercase stripped form for invariant matching."""
    return email.strip().lower()


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a high-entropy URL-safe random string."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Hash a random token using SHA-256 for persistent database storage.

    The raw token is transmitted to the user; only the hash is persisted, preventing
    database leaks from compromising one-time or session credentials.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    email: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Issue a signed JWT access token. Returns (encoded_jwt, expires_in_seconds)."""
    cfg = settings or get_settings()
    delta = expires_delta or timedelta(minutes=cfg.access_token_expire_minutes)
    now = datetime.now(UTC)
    exp = now + delta

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "whiteboard-api",
    }

    token = jwt.encode(payload, cfg.secret_key, algorithm=cfg.jwt_algorithm)
    expires_in = int(delta.total_seconds())
    return token, expires_in


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate signature and expiry of a JWT access token."""
    cfg = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            cfg.secret_key,
            algorithms=[cfg.jwt_algorithm],
            issuer="whiteboard-api",
            options={"require": ["sub", "exp", "iat"]},
        )
        return payload
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid or expired access token: {exc}") from exc


def generate_csrf_token() -> str:
    """Generate a CSRF token for state-changing browser requests."""
    return secrets.token_hex(32)
