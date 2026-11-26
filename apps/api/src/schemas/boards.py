"""Pydantic schemas for board and member operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.authorization.roles import BoardRole


class BoardCreateRequest(BaseModel):
    """Payload to create a new board."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="Visible title of the board",
    )


class BoardUpdateRequest(BaseModel):
    """Payload to update an existing board."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="New title of the board",
    )


class BoardResponse(BaseModel):
    """Board metadata representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    current_user_role: str | None = Field(
        default=None,
        description="The authenticated user's role on this board",
    )


class BoardListResponse(BaseModel):
    """Paginated list of boards."""

    items: list[BoardResponse]
    total: int = Field(ge=0, description="Total matching boards count")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, le=100, description="Number of items per page")


class BoardMemberResponse(BaseModel):
    """Board membership representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    board_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    display_name: str | None = None
    email: str | None = None
    created_at: datetime
    updated_at: datetime


class BoardMemberListResponse(BaseModel):
    """List of board members."""

    items: list[BoardMemberResponse]
    total: int = Field(ge=0, description="Total members count")


class BoardMemberAddRequest(BaseModel):
    """Payload to add a new member to a board."""

    user_id: uuid.UUID | None = Field(
        default=None,
        description="Target user ID to add as a member",
    )
    email: str | None = Field(
        default=None,
        description="Target user email to add as a member",
    )
    role: BoardRole = Field(
        default=BoardRole.VIEWER,
        description="Assigned role: 'editor' or 'viewer' (owner must be transferred)",
    )

    @model_validator(mode="after")
    def check_user_identifier(self) -> "BoardMemberAddRequest":
        if not self.user_id and not self.email:
            raise ValueError("Must provide either 'user_id' or 'email'")
        if self.role == BoardRole.OWNER:
            raise ValueError(
                "Cannot add a member as 'owner' directly. "
                "Use the transfer ownership endpoint instead."
            )
        return self


class BoardMemberUpdateRequest(BaseModel):
    """Payload to update a member's role."""

    role: BoardRole = Field(
        description="New role to assign to the member",
    )


class TransferOwnershipRequest(BaseModel):
    """Payload to transfer board ownership to another user."""

    new_owner_id: uuid.UUID = Field(
        description="User ID of the new owner",
    )
