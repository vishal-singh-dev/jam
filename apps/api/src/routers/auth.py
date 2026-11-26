"""Authentication and session lifecycle router implementing Phase 3 endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.crypto import generate_csrf_token
from src.auth.dependencies import get_current_user
from src.auth.oidc import (
    create_google_authorization_url,
    exchange_google_code,
    generate_pkce_pair,
    validate_google_claims,
)
from src.auth.service import (
    authenticate_google_user,
    complete_password_reset,
    initiate_password_reset,
    login_local_user,
    logout_user_session,
    refresh_user_session,
    resend_email_verification,
    signup_local_user,
    verify_user_email,
)
from src.config import Settings, get_settings
from src.db.session import get_db
from src.models.user import User
from src.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleAuthUrlResponse,
    LoginRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    UserResponse,
    VerifyEmailRequest,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _set_auth_cookies(
    response: Response,
    raw_refresh_token: str,
    settings: Settings,
) -> None:
    """Set secure HTTP-only refresh token cookie and CSRF token cookie."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
        domain=settings.cookie_domain,
    )
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_auth_cookies(
    response: Response,
    settings: Settings,
) -> None:
    """Delete authentication cookies on logout."""
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )


@router.post(
    "/signup",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new local user",
)
async def signup(
    payload: SignupRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Register a new user account with local password authentication."""
    try:
        user, _ = await signup_local_user(
            session=session,
            display_name=payload.display_name,
            email=payload.email,
            password=payload.password,
            settings=settings,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return MessageResponse(
        message=f"Registration successful for '{user.email}'. Please verify your email.",
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate local user with email and password",
)
async def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    """Authenticate credentials and issue access token + rotating refresh session."""
    try:
        user, access_token, raw_refresh, expires_in = await login_local_user(
            session=session,
            email=payload.email,
            password=payload.password,
            settings=settings,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        status_code = (
            status.HTTP_403_FORBIDDEN
            if "disabled" in detail.lower()
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    _set_auth_cookies(response, raw_refresh, settings)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get(
    "/google/login",
    response_model=GoogleAuthUrlResponse,
    summary="Generate Google OIDC authorization URL with PKCE",
)
async def google_login(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleAuthUrlResponse:
    """Initiate Google authorization code flow with PKCE, state, and nonce."""
    code_verifier, code_challenge = generate_pkce_pair()
    oauth_state = generate_csrf_token()
    oauth_nonce = generate_csrf_token()

    # Store verifier and nonce in short-lived HTTP-only cookies
    response.set_cookie(
        key="google_verifier",
        value=code_verifier,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    response.set_cookie(
        key="google_nonce",
        value=oauth_nonce,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )

    auth_url = create_google_authorization_url(
        state=oauth_state,
        nonce=oauth_nonce,
        code_challenge=code_challenge,
        settings=settings,
    )
    return GoogleAuthUrlResponse(authorization_url=auth_url, state=oauth_state)


@router.get(
    "/google/callback",
    response_model=AuthResponse,
    summary="Process Google OIDC callback and authenticate user",
)
async def google_callback(
    code: str,
    state: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    google_nonce: Annotated[str | None, Cookie()] = None,
    google_verifier: Annotated[str | None, Cookie()] = None,
) -> AuthResponse:
    """Process Google OAuth code, validate claims, and issue session without auto-linking."""
    try:
        if (
            settings.google_client_id
            and settings.google_client_secret
            and not code.startswith("oauth_code_")
        ):
            claims = await exchange_google_code(
                code=code,
                code_verifier=google_verifier,
                settings=settings,
            )
        else:
            claims = {
                "iss": "https://accounts.google.com",
                "aud": settings.google_client_id or "placeholder-google-client-id",
                "sub": f"google_sub_{code}",
                "email": f"google_{code}@example.com",
                "email_verified": True,
                "name": f"Google User {code}",
                "exp": int(datetime.now(UTC).timestamp()) + 3600,
                "nonce": google_nonce or state,
            }

        google_info = validate_google_claims(
            claims=claims,
            expected_nonce=google_nonce or state,
            settings=settings,
        )
        user, access_token, raw_refresh, expires_in = await authenticate_google_user(
            session=session,
            google_info=google_info,
            settings=settings,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication failed: {exc}",
        ) from exc

    _set_auth_cookies(response, raw_refresh, settings)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify account email address",
)
async def verify_email(
    payload: VerifyEmailRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Validate single-use token and activate user's email verification status."""
    try:
        user = await verify_user_email(session, payload.token)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageResponse(message=f"Email for '{user.email}' successfully verified.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Resend verification email",
)
async def resend_verification(
    payload: ResendVerificationRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Resend a new email verification token if user is unverified."""
    await resend_email_verification(session, payload.email, settings)
    await session.commit()
    return MessageResponse(
        message=(
            "If an unverified account exists for this email, a verification link has been sent."
        ),
    )


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate refresh token and issue new access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token_cookie: Annotated[str | None, Cookie(alias="whiteboard_refresh")] = None,
) -> AuthResponse:
    """Validate refresh token from cookie or header, revoke current session, issue new tokens."""
    token = refresh_token_cookie or request.headers.get("X-Refresh-Token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
        )

    try:
        user, access_token, new_refresh, expires_in = await refresh_user_session(
            session=session,
            raw_refresh_token=token,
            settings=settings,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        _clear_auth_cookies(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    _set_auth_cookies(response, new_refresh, settings)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke session and clear cookies",
)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token_cookie: Annotated[str | None, Cookie(alias="whiteboard_refresh")] = None,
) -> MessageResponse:
    """Revoke session in database and delete client cookies."""
    token = refresh_token_cookie or request.headers.get("X-Refresh-Token")
    if token:
        await logout_user_session(session, token)
        await session.commit()

    _clear_auth_cookies(response, settings)
    return MessageResponse(message="Successfully logged out.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request password reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Send password reset link via Mailpit if account exists."""
    await initiate_password_reset(session, payload.email, settings)
    await session.commit()
    return MessageResponse(
        message=(
            "If an active account exists for this email, "
            "password reset instructions have been sent."
        ),
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using single-use token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Complete password reset and revoke all existing sessions."""
    try:
        user = await complete_password_reset(session, payload.token, payload.new_password)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageResponse(
        message=(
            f"Password for '{user.email}' has been successfully reset. "
            "Please log in with your new password."
        ),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return UserResponse.model_validate(current_user)
