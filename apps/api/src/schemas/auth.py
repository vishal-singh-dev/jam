"""Authentication request and response schemas."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_str(value: str) -> str:
    """Validate and clean email address."""
    cleaned = value.strip()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email format")
    return cleaned


class SignupRequest(BaseModel):
    """Payload for local user registration."""

    display_name: str = Field(min_length=1, max_length=120, description="User's visible name")
    email: str = Field(min_length=3, max_length=320, description="User's email address")
    password: str = Field(
        min_length=8, max_length=128, description="Account password (min 8 chars)"
    )

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)


class LoginRequest(BaseModel):
    """Payload for local username/password login."""

    email: str = Field(min_length=3, max_length=320, description="User's registered email")
    password: str = Field(min_length=1, max_length=128, description="Account password")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)


class VerifyEmailRequest(BaseModel):
    """Payload for confirming email address via token."""

    token: str = Field(min_length=1, description="One-time verification token received via email")


class ResendVerificationRequest(BaseModel):
    """Payload to request a new verification token."""

    email: str = Field(min_length=3, max_length=320, description="Registered email address")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)


class ForgotPasswordRequest(BaseModel):
    """Payload to initiate password reset workflow."""

    email: str = Field(min_length=3, max_length=320, description="Account email address")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)


class ResetPasswordRequest(BaseModel):
    """Payload to complete password reset with token and new password."""

    token: str = Field(min_length=1, description="Single-use password reset token")
    new_password: str = Field(min_length=8, max_length=128, description="New account password")


class UserResponse(BaseModel):
    """User profile response representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    email: str
    email_verified: bool
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    """Successful authentication response containing user profile and access token."""

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")


class MessageResponse(BaseModel):
    """Generic informative operation response."""

    message: str
    status: str = "ok"


class GoogleAuthUrlResponse(BaseModel):
    """Authorization URL and state parameter for Google OIDC flow."""

    authorization_url: str
    state: str
