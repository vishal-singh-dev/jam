"""Configuration settings management via Pydantic BaseSettings."""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    environment: str = Field(default="development", description="Deployment environment")
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_version: str = Field(default="0.1.0", description="Application semantic version")
    debug: bool = Field(default=False, description="Debug mode flag")
    log_level: str = Field(default="INFO", description="Log level")

    # Security & CORS
    secret_key: str = Field(
        default="dev-secret-key-must-be-replaced-in-production-min-32-chars!",
        description="Application secret key for cryptographic operations",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ],
        description="Allowed origins for Cross-Origin Resource Sharing",
    )

    # Future integration settings (Phase 2+)
    database_url: str | None = Field(default=None, description="PostgreSQL connection string")
    collaboration_secret: str | None = Field(
        default=None, description="Secret key for collaboration token issuance"
    )

    # Authentication & Session Settings (Phase 3)
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(
        default=15, description="Access token expiration in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token session expiration in days"
    )
    verification_token_expire_hours: int = Field(
        default=24, description="Email verification token expiration in hours"
    )
    password_reset_token_expire_hours: int = Field(
        default=1, description="Password reset token expiration in hours"
    )

    # Cookie & CSRF Settings
    cookie_domain: str | None = Field(default=None, description="Domain for session cookies")
    cookie_secure: bool = Field(default=False, description="Whether session cookies require HTTPS")
    cookie_samesite: str = Field(default="lax", description="SameSite policy for session cookies")
    refresh_cookie_name: str = Field(
        default="whiteboard_refresh", description="HTTP-only refresh token cookie name"
    )
    csrf_cookie_name: str = Field(default="whiteboard_csrf", description="CSRF token cookie name")

    # Mail & SMTP (Mailpit) Settings
    mailpit_smtp_host: str = Field(default="localhost", description="Mailpit SMTP host")
    mailpit_smtp_port: int = Field(default=1025, description="Mailpit SMTP port")
    mailpit_web_port: int = Field(default=8025, description="Mailpit Web UI port")
    mail_from_email: str = Field(
        default="noreply@whiteboard.local",
        description="Sender email address for transactional mail",
    )
    mail_from_name: str = Field(
        default="Collaborative Whiteboard", description="Sender display name"
    )

    # Google OIDC Settings
    google_client_id: str | None = Field(default=None, description="Google OIDC client ID")
    google_client_secret: str | None = Field(default=None, description="Google OIDC client secret")
    google_redirect_uri: str | None = Field(
        default="http://localhost:5173/auth/google/callback",
        description="Google OIDC redirect URI",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Any) -> list[str]:
        """Parse CORS origins from JSON list, comma-separated string, or list."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
