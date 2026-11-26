"""Pydantic schemas package."""

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
from src.schemas.boards import (
    BoardCreateRequest,
    BoardListResponse,
    BoardMemberAddRequest,
    BoardMemberListResponse,
    BoardMemberResponse,
    BoardMemberUpdateRequest,
    BoardResponse,
    BoardUpdateRequest,
    TransferOwnershipRequest,
)
from src.schemas.errors import ErrorEnvelope, ErrorResponse
from src.schemas.system import HealthResponse, ReadyResponse, VersionResponse

__all__ = [
    "AuthResponse",
    "BoardCreateRequest",
    "BoardListResponse",
    "BoardMemberAddRequest",
    "BoardMemberListResponse",
    "BoardMemberResponse",
    "BoardMemberUpdateRequest",
    "BoardResponse",
    "BoardUpdateRequest",
    "ErrorEnvelope",
    "ErrorResponse",
    "ForgotPasswordRequest",
    "GoogleAuthUrlResponse",
    "HealthResponse",
    "LoginRequest",
    "MessageResponse",
    "ReadyResponse",
    "ResendVerificationRequest",
    "ResetPasswordRequest",
    "SignupRequest",
    "TransferOwnershipRequest",
    "UserResponse",
    "VerifyEmailRequest",
    "VersionResponse",
]
