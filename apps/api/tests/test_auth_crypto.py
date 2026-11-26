"""Unit tests for cryptographic functions, Argon2id hashing, and Google OIDC validation."""

import time
import uuid
from datetime import timedelta

import pytest

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
from src.auth.oidc import (
    create_google_authorization_url,
    generate_pkce_pair,
    validate_google_claims,
)
from src.config import Settings


def test_argon2id_password_hashing() -> None:
    """Argon2id produces verifiable hashes and rejects incorrect passwords."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_normalize_email() -> None:
    """Emails are trimmed and lowercased for uniform matching."""
    assert normalize_email("  Test.User@Example.COM ") == "test.user@example.com"
    assert normalize_email("ALICE@domain.org") == "alice@domain.org"


def test_token_hashing() -> None:
    """Tokens are hashed with SHA-256 for persistent storage."""
    raw = generate_secure_token(32)
    hashed1 = hash_token(raw)
    hashed2 = hash_token(raw)

    assert len(hashed1) == 64  # Hex-encoded sha256
    assert hashed1 == hashed2
    assert hashed1 != raw

    csrf = generate_csrf_token()
    assert len(csrf) >= 32


def test_jwt_access_token_creation_and_decoding() -> None:
    """JWT tokens contain standard claims and can be verified."""
    user_id = uuid.uuid4()
    email = "test@example.com"
    settings = Settings(secret_key="unit-test-secret-key-32-chars-long!!")

    token, expires_in = create_access_token(user_id, email, settings)
    assert expires_in == 900  # Default 15 minutes

    payload = decode_access_token(token, settings)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email
    assert payload["iss"] == "whiteboard-api"


def test_jwt_access_token_expiry() -> None:
    """Expired JWT tokens are rejected by decode_access_token."""
    user_id = uuid.uuid4()
    settings = Settings(secret_key="unit-test-secret-key-32-chars-long!!")

    # Token with negative delta (already expired)
    token, _ = create_access_token(
        user_id,
        "test@example.com",
        settings,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(ValueError, match="Invalid or expired access token"):
        decode_access_token(token, settings)


def test_jwt_invalid_signature() -> None:
    """Tokens signed with a different key are rejected."""
    user_id = uuid.uuid4()
    settings1 = Settings(secret_key="first-secret-key-min-32-characters!!")
    settings2 = Settings(secret_key="second-secret-key-min-32-characters!")

    token, _ = create_access_token(user_id, "test@example.com", settings1)

    with pytest.raises(ValueError, match="Invalid or expired access token"):
        decode_access_token(token, settings2)


def test_generate_pkce_pair() -> None:
    """PKCE generator produces code_verifier and URL-safe base64 challenge."""
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert "=" not in challenge


def test_google_auth_url_construction() -> None:
    """Google authorization URL includes PKCE challenge, state, and scopes."""
    settings = Settings(
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_redirect_uri="http://localhost:5173/auth/google/callback",
    )
    url = create_google_authorization_url(
        state="state-123",
        nonce="nonce-456",
        code_challenge="challenge-789",
        settings=settings,
    )
    assert "https://accounts.google.com/o/oauth2/v2/auth?" in url
    assert "client_id=test-client-id.apps.googleusercontent.com" in url
    assert "code_challenge=challenge-789" in url
    assert "code_challenge_method=S256" in url
    assert "state=state-123" in url
    assert "nonce=nonce-456" in url


def test_google_claims_validation_success() -> None:
    """Valid Google ID token claims are extracted into GoogleUserInfo."""
    settings = Settings(google_client_id="my-google-app-id")
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "my-google-app-id",
        "sub": "google-user-sub-12345",
        "email": "google.user@example.com",
        "email_verified": True,
        "name": "Google User",
        "exp": int(time.time()) + 3600,
        "nonce": "test-nonce-value",
    }
    info = validate_google_claims(claims, expected_nonce="test-nonce-value", settings=settings)
    assert info.sub == "google-user-sub-12345"
    assert info.email == "google.user@example.com"
    assert info.email_verified is True
    assert info.name == "Google User"


def test_google_claims_invalid_issuer() -> None:
    """Google claims with invalid issuer are rejected."""
    claims = {
        "iss": "https://malicious-issuer.com",
        "aud": "my-client-id",
        "sub": "sub123",
        "email": "user@example.com",
        "email_verified": True,
        "exp": int(time.time()) + 3600,
    }
    with pytest.raises(ValueError, match="Invalid Google ID token issuer"):
        validate_google_claims(claims)


def test_google_claims_unverified_email() -> None:
    """Google claims with email_verified=False are rejected."""
    settings = Settings(google_client_id="my-client-id")
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "my-client-id",
        "sub": "sub123",
        "email": "unverified@example.com",
        "email_verified": False,
        "exp": int(time.time()) + 3600,
    }
    with pytest.raises(ValueError, match="Google email is not verified"):
        validate_google_claims(claims, settings=settings)


def test_google_claims_nonce_mismatch() -> None:
    """Google claims with mismatched nonce are rejected."""
    settings = Settings(google_client_id="my-client-id")
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "my-client-id",
        "sub": "sub123",
        "email": "user@example.com",
        "email_verified": True,
        "exp": int(time.time()) + 3600,
        "nonce": "wrong-nonce",
    }
    with pytest.raises(ValueError, match="nonce mismatch"):
        validate_google_claims(claims, expected_nonce="expected-nonce", settings=settings)
