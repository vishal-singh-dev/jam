"""Google OIDC integration with authorization code flow, PKCE, state, and nonce validation."""

import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from src.config import Settings, get_settings


@dataclass
class GoogleUserInfo:
    """Validated claims extracted from Google ID Token."""

    sub: str
    email: str
    email_verified: bool
    name: str


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and S256 code_challenge."""
    code_verifier = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def create_google_authorization_url(
    state: str,
    nonce: str,
    code_challenge: str,
    settings: Settings | None = None,
) -> str:
    """Construct Google OAuth2 authorization URL with PKCE and OpenID scopes."""
    cfg = settings or get_settings()
    client_id = cfg.google_client_id or "placeholder-google-client-id"
    redirect_uri = cfg.google_redirect_uri or "http://localhost:5173/auth/google/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def validate_google_claims(
    claims: dict[str, Any],
    expected_nonce: str | None = None,
    settings: Settings | None = None,
) -> GoogleUserInfo:
    """Validate Google ID token claims: issuer, audience, expiry, nonce, and email_verified.

    Never auto-links based on email alone. Uses 'sub' as immutable external subject.
    """
    cfg = settings or get_settings()

    # 1. Validate Issuer
    iss = claims.get("iss")
    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        raise ValueError(f"Invalid Google ID token issuer: {iss}")

    # 2. Validate Audience
    aud = claims.get("aud")
    expected_aud = cfg.google_client_id or "placeholder-google-client-id"
    if aud != expected_aud:
        msg = f"Google ID token audience '{aud}' does not match expected '{expected_aud}'"
        raise ValueError(msg)

    # 3. Validate Expiration
    exp_raw = claims.get("exp")
    if not exp_raw:
        raise ValueError("Google ID token missing exp claim")
    try:
        exp = int(exp_raw)
        exp_dt = datetime.fromtimestamp(exp, tz=UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError(f"Invalid expiration timestamp in Google ID token: {exc}") from exc
    if exp_dt <= datetime.now(UTC):
        raise ValueError("Google ID token has expired")

    # 4. Validate Nonce
    if expected_nonce is not None:
        token_nonce = claims.get("nonce")
        if token_nonce != expected_nonce:
            msg = (
                f"Google ID token nonce mismatch: expected '{expected_nonce}', got '{token_nonce}'"
            )
            raise ValueError(msg)

    # 5. Validate Email and Email Verified
    email = claims.get("email")
    if not email:
        raise ValueError("Google ID token missing email claim")

    email_verified = claims.get("email_verified") in (True, "true", "True")
    if not email_verified:
        raise ValueError("Google email is not verified by Google")

    sub = claims.get("sub")
    if not sub:
        raise ValueError("Google ID token missing sub claim")

    name = claims.get("name") or str(email).split("@")[0]

    return GoogleUserInfo(
        sub=str(sub),
        email=str(email),
        email_verified=True,
        name=str(name),
    )


async def exchange_google_code(
    code: str,
    code_verifier: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Exchange authorization code with Google for tokens and claims."""
    cfg = settings or get_settings()
    if not cfg.google_client_id or not cfg.google_client_secret:
        raise ValueError("Google OAuth client ID or secret is not configured")

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": cfg.google_client_id,
        "client_secret": cfg.google_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": cfg.google_redirect_uri or "http://localhost:5173/auth/google/callback",
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_data = resp.json()
                err_msg = err_data.get("error_description") or err_data.get("error") or err_msg
            except Exception:
                pass
            raise ValueError(f"Google token exchange failed ({resp.status_code}): {err_msg}")

        token_data = resp.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise ValueError("Google did not return an id_token in token exchange response")

        # Query Google's tokeninfo endpoint to verify token signature and extract claims
        info_resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}")
        if info_resp.status_code != 200:
            raise ValueError(f"Google tokeninfo validation failed: {info_resp.text}")

        return info_resp.json()
