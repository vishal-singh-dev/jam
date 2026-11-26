"""Authorization FastAPI dependencies.

Provides reusable dependency injectors that enforce board membership and
granular role permissions server-side. Keeps authorization concerns decoupled
from route handlers.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import get_current_user
from src.authorization.policies import has_board_permission
from src.authorization.roles import BoardPermission
from src.db.session import get_db
from src.models.board import Board, BoardMember
from src.models.user import User


async def get_board_membership(
    board_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BoardMember:
    """Validate that the board exists and that the authenticated user is an active member.

    Returns the BoardMember object with preloaded board and user relationships.
    """
    # 1. Verify board exists and is not soft-deleted
    board_query = await session.execute(
        select(Board).where(
            Board.id == board_id,
            Board.deleted_at.is_(None),
        )
    )
    board = board_query.scalar_one_or_none()
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_id}' not found",
        )

    # 2. Verify current user's membership
    member_query = await session.execute(
        select(BoardMember)
        .where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == current_user.id,
        )
        .options(
            selectinload(BoardMember.board),
            selectinload(BoardMember.user),
        )
    )
    membership = member_query.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you are not a member of this board",
        )

    return membership


def require_board_permission_dep(
    permission: BoardPermission,
) -> Callable[[BoardMember], BoardMember]:
    """Dependency factory checking if the current member possesses the required permission."""

    def dependency(
        membership: Annotated[BoardMember, Depends(get_board_membership)],
    ) -> BoardMember:
        if not has_board_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions: role '{membership.role}' lacks "
                    f"required permission '{permission.value}'"
                ),
            )
        return membership

    return dependency
