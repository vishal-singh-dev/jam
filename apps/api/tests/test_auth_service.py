"""Integration tests for authentication domain service methods."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.crypto import hash_token, verify_password
from src.auth.oidc import GoogleUserInfo
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
from src.models.auth import (
    AuthIdentity,
    EmailVerificationToken,
    PasswordResetToken,
    UserSession,
)

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/whiteboard_db"


@pytest.fixture
async def session() -> AsyncSession:
    """Provide an isolated async session for authentication tests."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as sess:
        yield sess
        await sess.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_signup_local_user_flow(session: AsyncSession) -> None:
    """Local signup creates User, Argon2id AuthIdentity, and single-use verification token."""
    email = f"signup_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    user, raw_token = await signup_local_user(
        session=session,
        display_name="Test Signup User",
        email=email,
        password=password,
    )

    assert user.id is not None
    assert user.email == email
    assert user.normalized_email == email.lower()
    assert user.email_verified is False
    assert user.is_active is True

    # Verify AuthIdentity
    ident_res = await session.execute(select(AuthIdentity).where(AuthIdentity.user_id == user.id))
    identity = ident_res.scalar_one()
    assert identity.provider == "local"
    assert identity.password_hash is not None
    assert verify_password(password, identity.password_hash) is True

    # Verify Verification Token hash (raw token is never persisted)
    token_res = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    token_rec = token_res.scalar_one()
    assert token_rec.token_hash == hash_token(raw_token)
    assert token_rec.token_hash != raw_token
    assert token_rec.used_at is None


@pytest.mark.asyncio
async def test_signup_duplicate_email_rejected(session: AsyncSession) -> None:
    """Duplicate email registration must be rejected."""
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    await signup_local_user(session, "First User", email, "Password123!")

    with pytest.raises(ValueError, match="already exists"):
        await signup_local_user(session, "Second User", email.upper(), "Password456!")


@pytest.mark.asyncio
async def test_login_local_user_flow(session: AsyncSession) -> None:
    """Valid credentials issue access token and create a refresh session."""
    email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"
    user, _ = await signup_local_user(session, "Login User", email, password)

    logged_user, access_token, raw_refresh, expires_in = await login_local_user(
        session=session,
        email=email,
        password=password,
    )

    assert logged_user.id == user.id
    assert access_token is not None
    assert expires_in == 900
    assert raw_refresh is not None

    # Verify session in DB
    sess_res = await session.execute(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_refresh))
    )
    user_sess = sess_res.scalar_one()
    assert user_sess.user_id == user.id
    assert user_sess.revoked_at is None


@pytest.mark.asyncio
async def test_login_invalid_password(session: AsyncSession) -> None:
    """Incorrect password raises generic error without leaking details."""
    email = f"wrongpw_{uuid.uuid4().hex[:8]}@example.com"
    await signup_local_user(session, "Wrong PW User", email, "RightPassword123!")

    with pytest.raises(ValueError, match="Invalid email or password"):
        await login_local_user(session, email, "IncorrectPassword999!")


@pytest.mark.asyncio
async def test_login_deactivated_user(session: AsyncSession) -> None:
    """Deactivated user account cannot log in."""
    email = f"deactive_{uuid.uuid4().hex[:8]}@example.com"
    user, _ = await signup_local_user(session, "Deactive User", email, "Password123!")
    user.is_active = False
    await session.flush()

    with pytest.raises(ValueError, match="User account is disabled"):
        await login_local_user(session, email, "Password123!")


@pytest.mark.asyncio
async def test_email_verification_lifecycle(session: AsyncSession) -> None:
    """Verify email activates account; reuse or expired tokens are rejected."""
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    user, raw_token = await signup_local_user(session, "Verify User", email, "Password123!")

    # 1. Successful verification
    verified_user = await verify_user_email(session, raw_token)
    assert verified_user.id == user.id
    assert verified_user.email_verified is True

    # 2. Reusing the token must fail
    with pytest.raises(ValueError, match="already used"):
        await verify_user_email(session, raw_token)

    # 3. Expired token rejection
    user2, raw_token2 = await signup_local_user(
        session, "Verify User 2", f"exp_{uuid.uuid4().hex[:8]}@example.com", "Password123!"
    )
    # Expire token manually
    token_res = await session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(raw_token2)
        )
    )
    token_rec = token_res.scalar_one()
    token_rec.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await session.flush()

    with pytest.raises(ValueError, match="expired"):
        await verify_user_email(session, raw_token2)


@pytest.mark.asyncio
async def test_resend_verification_email(session: AsyncSession) -> None:
    """Resending verification invalidates previous tokens and issues a new one."""
    email = f"resend_{uuid.uuid4().hex[:8]}@example.com"
    user, raw_token1 = await signup_local_user(session, "Resend User", email, "Password123!")

    await resend_email_verification(session, email)

    # Previous token must now be marked used/invalidated
    token1_res = await session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(raw_token1)
        )
    )
    assert token1_res.scalar_one().used_at is not None


@pytest.mark.asyncio
async def test_password_reset_lifecycle_and_session_revocation(session: AsyncSession) -> None:
    """Password reset updates hash, invalidates token, and revokes all active sessions."""
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    user, _ = await signup_local_user(session, "Reset User", email, "OldPassword123!")

    # Login to create an active session
    _, _, raw_refresh, _ = await login_local_user(session, email, "OldPassword123!")

    # Initiate reset
    await initiate_password_reset(session, email)

    # Retrieve generated reset token
    token_res = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token_rec = token_res.scalar_one()

    # Complete reset
    new_password = "NewSuperPassword123!"
    # In test, we simulate knowing raw token or use the hash to complete
    # To test complete_password_reset with raw token:
    raw_reset = "custom-test-reset-token-value"
    token_rec.token_hash = hash_token(raw_reset)
    await session.flush()

    reset_user = await complete_password_reset(session, raw_reset, new_password)
    assert reset_user.id == user.id

    # 1. Login with old password must fail
    with pytest.raises(ValueError, match="Invalid email or password"):
        await login_local_user(session, email, "OldPassword123!")

    # 2. Login with new password must succeed
    user_logged, _, _, _ = await login_local_user(session, email, new_password)
    assert user_logged.id == user.id

    # 3. Previous session must be revoked
    old_sess_res = await session.execute(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_refresh))
    )
    assert old_sess_res.scalar_one().revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection(session: AsyncSession) -> None:
    """Session refresh rotates the token; reusing a revoked token triggers reuse detection."""
    email = f"rotate_{uuid.uuid4().hex[:8]}@example.com"
    await signup_local_user(session, "Rotate User", email, "Password123!")
    _, _, raw_refresh_1, _ = await login_local_user(session, email, "Password123!")

    # 1. Valid refresh rotates token
    user, new_access, raw_refresh_2, _ = await refresh_user_session(session, raw_refresh_1)
    assert new_access is not None
    assert raw_refresh_2 != raw_refresh_1

    # Verify old session was marked revoked and replaced_by points to new session
    old_sess_res = await session.execute(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_refresh_1))
    )
    old_sess = old_sess_res.scalar_one()
    assert old_sess.revoked_at is not None
    assert old_sess.replaced_by_session_id is not None

    # 2. Second refresh using the new token succeeds
    _, _, raw_refresh_3, _ = await refresh_user_session(session, raw_refresh_2)
    assert raw_refresh_3 != raw_refresh_2

    # 3. Attempting to REUSE revoked raw_refresh_1 triggers reuse detection
    with pytest.raises(ValueError, match="Revoked session token reuse detected"):
        await refresh_user_session(session, raw_refresh_1)


@pytest.mark.asyncio
async def test_logout_session(session: AsyncSession) -> None:
    """Logout revokes the session in the database."""
    email = f"logout_{uuid.uuid4().hex[:8]}@example.com"
    await signup_local_user(session, "Logout User", email, "Password123!")
    _, _, raw_refresh, _ = await login_local_user(session, email, "Password123!")

    await logout_user_session(session, raw_refresh)

    sess_res = await session.execute(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_refresh))
    )
    assert sess_res.scalar_one().revoked_at is not None


@pytest.mark.asyncio
async def test_google_oidc_authentication_and_no_auto_link(session: AsyncSession) -> None:
    """Google auth creates user by sub; strictly forbids auto-linking existing local account."""
    google_sub = f"sub_{uuid.uuid4().hex}"
    google_email = f"google_{uuid.uuid4().hex[:8]}@example.com"

    # 1. New Google user registers successfully
    g_info = GoogleUserInfo(
        sub=google_sub,
        email=google_email,
        email_verified=True,
        name="Google Test User",
    )
    user, access_token, refresh_token, _ = await authenticate_google_user(session, g_info)
    assert user.email == google_email
    assert user.email_verified is True

    # 2. Subsequent login with same Google sub succeeds
    user2, _, _, _ = await authenticate_google_user(session, g_info)
    assert user2.id == user.id

    # 3. Conflict: User exists locally with email 'local.only@example.com'
    local_email = f"local_{uuid.uuid4().hex[:8]}@example.com"
    await signup_local_user(session, "Local User", local_email, "Password123!")

    # Attempting to sign in with Google using that same email with a new Google sub MUST fail
    conflict_google = GoogleUserInfo(
        sub=f"sub_conflict_{uuid.uuid4().hex}",
        email=local_email,
        email_verified=True,
        name="Attempted AutoLink",
    )
    with pytest.raises(ValueError, match="Automatic account linking by email alone is prohibited"):
        await authenticate_google_user(session, conflict_google)
