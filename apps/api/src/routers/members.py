"""Board members and permissions management router implementing Phase 4 endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.authorization.dependencies import (
    get_board_membership,
    require_board_permission_dep,
)
from src.authorization.policies import has_board_permission
from src.authorization.roles import BoardPermission
from src.boards.service import (
    add_board_member,
    list_board_members,
    remove_member,
    update_member_role,
)
from src.db.session import get_db
from src.models.board import BoardMember
from src.models.user import User
from src.schemas.auth import MessageResponse
from src.schemas.boards import (
    BoardMemberAddRequest,
    BoardMemberListResponse,
    BoardMemberResponse,
    BoardMemberUpdateRequest,
)

router = APIRouter(
    prefix="/boards/{board_id}/members",
    tags=["Board Members"],
)


@router.get(
    "",
    response_model=BoardMemberListResponse,
    summary="List all members of a board",
)
async def list_members(
    board_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.VIEW_MEMBERS)),
    ],
) -> BoardMemberListResponse:
    """Retrieve all members of a board with their roles and user information."""
    members = await list_board_members(session, board_id)
    items = [
        BoardMemberResponse(
            id=m.id,
            board_id=m.board_id,
            user_id=m.user_id,
            role=m.role,
            display_name=m.user.display_name if m.user else None,
            email=m.user.email if m.user else None,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in members
    ]
    return BoardMemberListResponse(items=items, total=len(items))


@router.post(
    "",
    response_model=BoardMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new member to the board",
)
async def add_member(
    board_id: uuid.UUID,
    payload: BoardMemberAddRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.MANAGE_MEMBERS)),
    ],
) -> BoardMemberResponse:
    """Add a new editor or viewer to the board (owner-only permission)."""
    # 1. Resolve target user
    if payload.user_id:
        user_query = select(User).where(User.id == payload.user_id, User.is_active.is_(True))
    else:
        norm_email = payload.email.strip().lower() if payload.email else ""
        user_query = select(User).where(
            User.normalized_email == norm_email, User.is_active.is_(True)
        )

    user_res = await session.execute(user_query)
    target_user = user_res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found or inactive",
        )

    # 2. Add member
    try:
        member = await add_board_member(
            session=session,
            board_id=board_id,
            target_user=target_user,
            role=payload.role,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return BoardMemberResponse(
        id=member.id,
        board_id=member.board_id,
        user_id=member.user_id,
        role=member.role,
        display_name=target_user.display_name,
        email=target_user.email,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.patch(
    "/{user_id}",
    response_model=BoardMemberResponse,
    summary="Update a board member's role",
)
async def update_member(
    board_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: BoardMemberUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_membership: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.MANAGE_MEMBERS)),
    ],
) -> BoardMemberResponse:
    """Update a member's role (owner-only permission)."""
    try:
        updated_member = await update_member_role(
            session=session,
            board_id=board_id,
            current_owner_id=current_membership.user_id,
            target_user_id=user_id,
            new_role=payload.role,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return BoardMemberResponse(
        id=updated_member.id,
        board_id=updated_member.board_id,
        user_id=updated_member.user_id,
        role=updated_member.role,
        display_name=updated_member.user.display_name if updated_member.user else None,
        email=updated_member.user.email if updated_member.user else None,
        created_at=updated_member.created_at,
        updated_at=updated_member.updated_at,
    )


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Remove a member from the board",
)
async def remove_member_endpoint(
    board_id: uuid.UUID,
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_membership: Annotated[BoardMember, Depends(get_board_membership)],
) -> MessageResponse:
    """Remove a member from the board.

    Owners can remove any member; members can remove themselves.
    """
    is_self = current_membership.user_id == user_id
    can_manage = has_board_permission(current_membership.role, BoardPermission.MANAGE_MEMBERS)

    if not is_self and not can_manage:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove other members without manage_members permission",
        )

    try:
        await remove_member(session, board_id, user_id)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageResponse(
        message=f"Member '{user_id}' has been successfully removed from board '{board_id}'"
    )
