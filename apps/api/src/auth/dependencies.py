"""FastAPI dependencies for authentication and current user resolution."""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.crypto import decode_access_token
from src.config import Settings, get_settings
from src.db.session import get_db
from src.models.user import User


async def get_current_user(
    authorization: Annotated[str | None, Header(description="Bearer <token>")] = None,
    access_token_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> User:
    """Resolve and validate the authenticated user from bearer token or cookie."""
    token: str | None = None

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif access_token_cookie:
        token = access_token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token, settings)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Token missing sub claim")
        user_id = uuid.UUID(user_id_str)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def get_current_verified_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the authenticated user has verified their email address."""
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required before accessing this resource.",
        )
    return current_user


async def get_optional_current_user(
    authorization: Annotated[str | None, Header()] = None,
    access_token_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> User | None:
    """Optionally resolve user if token is present, returning None if unauthenticated."""
    try:
        return await get_current_user(
            authorization=authorization,
            access_token_cookie=access_token_cookie,
            session=session,
            settings=settings,
        )
    except HTTPException:
        return None
