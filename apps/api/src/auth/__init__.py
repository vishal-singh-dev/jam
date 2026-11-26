"""Authentication package providing local auth, Google OIDC, tokens, and session management."""

from src.auth.crypto import (
    create_access_token,
    decode_access_token,
    generate_csrf_token,
    generate_secure_token,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
)
from src.auth.dependencies import (
    get_current_user,
    get_current_verified_user,
    get_optional_current_user,
)
from src.auth.email import send_password_reset_email, send_verification_email
from src.auth.oidc import (
    GoogleUserInfo,
    create_google_authorization_url,
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

__all__ = [
    "GoogleUserInfo",
    "authenticate_google_user",
    "complete_password_reset",
    "create_access_token",
    "create_google_authorization_url",
    "decode_access_token",
    "generate_csrf_token",
    "generate_pkce_pair",
    "generate_secure_token",
    "get_current_user",
    "get_current_verified_user",
    "get_optional_current_user",
    "hash_password",
    "hash_token",
    "initiate_password_reset",
    "login_local_user",
    "logout_user_session",
    "normalize_email",
    "refresh_user_session",
    "resend_email_verification",
    "send_password_reset_email",
    "send_verification_email",
    "signup_local_user",
    "validate_google_claims",
    "verify_password",
    "verify_user_email",
]
