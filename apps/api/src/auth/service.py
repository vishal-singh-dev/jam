"""Authentication service implementing signup, login, session rotation, and token workflows."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.crypto import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
)
from src.auth.email import send_password_reset_email, send_verification_email
from src.auth.oidc import GoogleUserInfo
from src.config import Settings, get_settings
from src.models.auth import (
    AuthIdentity,
    EmailVerificationToken,
    PasswordResetToken,
    UserSession,
)
from src.models.user import User


async def signup_local_user(
    session: AsyncSession,
    display_name: str,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[User, str]:
    """Register a new user with local email/password authentication.

    Generates a single-use verification token and delivers verification email via Mailpit.
    """
    cfg = settings or get_settings()
    norm_email = normalize_email(email)

    # Check for existing user
    existing = await session.execute(select(User).where(User.normalized_email == norm_email))
    if existing.scalar_one_or_none():
        raise ValueError("An account with this email address already exists")

    # 1. Create User
    user = User(
        id=uuid.uuid4(),
        display_name=display_name.strip(),
        email=email.strip(),
        normalized_email=norm_email,
        email_verified=False,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # 2. Create Local Auth Identity with Argon2id hash
    pw_hash = hash_password(password)
    identity = AuthIdentity(
        id=uuid.uuid4(),
        user_id=user.id,
        provider="local",
        password_hash=pw_hash,
    )
    session.add(identity)

    # 3. Create Verification Token
    raw_token = generate_secure_token(32)
    now = datetime.now(UTC)
    token_record = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=cfg.verification_token_expire_hours),
    )
    session.add(token_record)
    await session.flush()

    # 4. Deliver verification email (mocked or via Mailpit)
    send_verification_email(user.email, user.display_name, raw_token, cfg)

    return user, raw_token


async def login_local_user(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[User, str, str, int]:
    """Authenticate a local user and issue access token and rotating refresh session."""
    cfg = settings or get_settings()
    norm_email = normalize_email(email)

    # Find user by normalized email
    res = await session.execute(select(User).where(User.normalized_email == norm_email))
    user = res.scalar_one_or_none()
    if not user:
        raise ValueError("Invalid email or password")

    if not user.is_active:
        raise ValueError("User account is disabled")

    # Find local identity
    ident_res = await session.execute(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user.id,
            AuthIdentity.provider == "local",
        )
    )
    identity = ident_res.scalar_one_or_none()
    if (
        not identity
        or not identity.password_hash
        or not verify_password(password, identity.password_hash)
    ):
        raise ValueError("Invalid email or password")

    # Create rotating refresh session
    raw_refresh = generate_secure_token(48)
    now = datetime.now(UTC)
    user_session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=hash_token(raw_refresh),
        expires_at=now + timedelta(days=cfg.refresh_token_expire_days),
        created_at=now,
        last_used_at=now,
    )
    session.add(user_session)
    await session.flush()

    # Issue access token
    access_token, expires_in = create_access_token(user.id, user.email, cfg)
    return user, access_token, raw_refresh, expires_in


async def authenticate_google_user(
    session: AsyncSession,
    google_info: GoogleUserInfo,
    settings: Settings | None = None,
) -> tuple[User, str, str, int]:
    """Authenticate or register a user via Google OIDC claims.

    Uses Google sub as immutable subject. Strictly rejects auto-linking by email alone.
    """
    cfg = settings or get_settings()

    # 1. Resolve identity by Google sub
    ident_res = await session.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == "google",
            AuthIdentity.provider_subject == google_info.sub,
        )
    )
    identity = ident_res.scalar_one_or_none()

    if identity:
        user_res = await session.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one()
        if not user.is_active:
            raise ValueError("User account is disabled")
    else:
        # Check if email is already taken by a local account - NEVER auto-link by email
        norm_email = normalize_email(google_info.email)
        existing_user_res = await session.execute(
            select(User).where(User.normalized_email == norm_email)
        )
        if existing_user_res.scalar_one_or_none():
            raise ValueError(
                "An account with this email already exists using a different sign-in method. "
                "Automatic account linking by email alone is prohibited."
            )

        # Create new user and Google identity
        user = User(
            id=uuid.uuid4(),
            display_name=google_info.name.strip(),
            email=google_info.email.strip(),
            normalized_email=norm_email,
            email_verified=True,  # Google email is pre-verified
            is_active=True,
        )
        session.add(user)
        await session.flush()

        new_identity = AuthIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider="google",
            provider_subject=google_info.sub,
        )
        session.add(new_identity)
        await session.flush()

    # Issue session & tokens
    raw_refresh = generate_secure_token(48)
    now = datetime.now(UTC)
    user_session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=hash_token(raw_refresh),
        expires_at=now + timedelta(days=cfg.refresh_token_expire_days),
        created_at=now,
        last_used_at=now,
    )
    session.add(user_session)
    await session.flush()

    access_token, expires_in = create_access_token(user.id, user.email, cfg)
    return user, access_token, raw_refresh, expires_in


async def verify_user_email(
    session: AsyncSession,
    raw_token: str,
) -> User:
    """Verify single-use token and mark user.email_verified=True."""
    hashed = hash_token(raw_token.strip())
    now = datetime.now(UTC)

    res = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hashed)
    )
    token_record = res.scalar_one_or_none()

    if not token_record or token_record.used_at is not None:
        raise ValueError("Invalid or already used verification token")

    if token_record.expires_at <= now:
        raise ValueError("Verification token has expired")

    token_record.used_at = now

    user_res = await session.execute(select(User).where(User.id == token_record.user_id))
    user = user_res.scalar_one()
    user.email_verified = True
    await session.flush()

    return user


async def resend_email_verification(
    session: AsyncSession,
    email: str,
    settings: Settings | None = None,
) -> None:
    """Issue a new verification token and send email if user exists and is unverified."""
    cfg = settings or get_settings()
    norm_email = normalize_email(email)

    res = await session.execute(select(User).where(User.normalized_email == norm_email))
    user = res.scalar_one_or_none()
    if not user or user.email_verified or not user.is_active:
        return  # Silent return to prevent user enumeration

    # Invalidate previous unused tokens for this user
    now = datetime.now(UTC)
    await session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    # Issue new token
    raw_token = generate_secure_token(32)
    new_token_record = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=cfg.verification_token_expire_hours),
    )
    session.add(new_token_record)
    await session.flush()

    send_verification_email(user.email, user.display_name, raw_token, cfg)


async def initiate_password_reset(
    session: AsyncSession,
    email: str,
    settings: Settings | None = None,
) -> None:
    """Generate a single-use password reset token and send email via Mailpit."""
    cfg = settings or get_settings()
    norm_email = normalize_email(email)

    res = await session.execute(select(User).where(User.normalized_email == norm_email))
    user = res.scalar_one_or_none()
    if not user or not user.is_active:
        return  # Silent return against user enumeration

    now = datetime.now(UTC)
    raw_token = generate_secure_token(32)
    reset_record = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=cfg.password_reset_token_expire_hours),
    )
    session.add(reset_record)
    await session.flush()

    send_password_reset_email(user.email, user.display_name, raw_token, cfg)


async def complete_password_reset(
    session: AsyncSession,
    raw_token: str,
    new_password: str,
) -> User:
    """Validate single-use reset token, update local password hash, and revoke all sessions."""
    hashed = hash_token(raw_token.strip())
    now = datetime.now(UTC)

    res = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hashed)
    )
    token_record = res.scalar_one_or_none()

    if not token_record or token_record.used_at is not None:
        raise ValueError("Invalid or already used password reset token")

    if token_record.expires_at <= now:
        raise ValueError("Password reset token has expired")

    token_record.used_at = now

    user_res = await session.execute(select(User).where(User.id == token_record.user_id))
    user = user_res.scalar_one()

    # Update or add local identity password hash
    ident_res = await session.execute(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user.id,
            AuthIdentity.provider == "local",
        )
    )
    local_ident = ident_res.scalar_one_or_none()
    new_pw_hash = hash_password(new_password)

    if local_ident:
        local_ident.password_hash = new_pw_hash
    else:
        local_ident = AuthIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider="local",
            password_hash=new_pw_hash,
        )
        session.add(local_ident)

    # Security best practice: revoke all active sessions after password reset
    await session.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.flush()

    return user


async def refresh_user_session(
    session: AsyncSession,
    raw_refresh_token: str,
    settings: Settings | None = None,
) -> tuple[User, str, str, int]:
    """Rotate refresh token: validate, revoke current session, issue new tokens."""
    cfg = settings or get_settings()
    hashed = hash_token(raw_refresh_token.strip())
    now = datetime.now(UTC)

    res = await session.execute(select(UserSession).where(UserSession.refresh_token_hash == hashed))
    curr_session = res.scalar_one_or_none()

    if not curr_session:
        raise ValueError("Invalid refresh token")

    # Token reuse detection
    if curr_session.revoked_at is not None:
        # Invalidate any session in this lineage
        if curr_session.replaced_by_session_id:
            await session.execute(
                update(UserSession)
                .where(UserSession.id == curr_session.replaced_by_session_id)
                .values(revoked_at=now)
            )
        raise ValueError("Revoked session token reuse detected. Please log in again.")

    if curr_session.expires_at <= now:
        raise ValueError("Session expired. Please log in again.")

    user_res = await session.execute(select(User).where(User.id == curr_session.user_id))
    user = user_res.scalar_one()

    if not user.is_active:
        raise ValueError("User account is disabled")

    # Rotate session
    new_raw_refresh = generate_secure_token(48)
    new_session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=hash_token(new_raw_refresh),
        expires_at=now + timedelta(days=cfg.refresh_token_expire_days),
        created_at=now,
        last_used_at=now,
    )
    session.add(new_session)
    await session.flush()

    curr_session.revoked_at = now
    curr_session.replaced_by_session_id = new_session.id
    curr_session.last_used_at = now
    await session.flush()

    access_token, expires_in = create_access_token(user.id, user.email, cfg)
    return user, access_token, new_raw_refresh, expires_in


async def logout_user_session(
    session: AsyncSession,
    raw_refresh_token: str,
) -> None:
    """Revoke user session matching the refresh token."""
    hashed = hash_token(raw_refresh_token.strip())
    now = datetime.now(UTC)

    res = await session.execute(
        select(UserSession).where(
            UserSession.refresh_token_hash == hashed,
            UserSession.revoked_at.is_(None),
        )
    )
    curr_session = res.scalar_one_or_none()
    if curr_session:
        curr_session.revoked_at = now
        await session.flush()
