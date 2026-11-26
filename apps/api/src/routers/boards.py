"""Board CRUD and lifecycle management router implementing Phase 4 endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.authorization.dependencies import require_board_permission_dep
from src.authorization.roles import BoardPermission
from src.boards.service import (
    create_board,
    list_user_boards,
    soft_delete_board,
    transfer_ownership,
    update_board_title,
)
from src.db.session import get_db
from src.models.board import BoardMember
from src.models.user import User
from src.schemas.auth import MessageResponse
from src.schemas.boards import (
    BoardCreateRequest,
    BoardListResponse,
    BoardResponse,
    BoardUpdateRequest,
    TransferOwnershipRequest,
)

router = APIRouter(
    prefix="/boards",
    tags=["Boards"],
)


@router.post(
    "",
    response_model=BoardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new whiteboard",
)
async def create_new_board(
    payload: BoardCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BoardResponse:
    """Create a new whiteboard canvas with the authenticated user as owner."""
    board = await create_board(
        session=session,
        owner_id=current_user.id,
        title=payload.title,
    )
    await session.commit()

    return BoardResponse(
        id=board.id,
        title=board.title,
        owner_id=board.owner_id,
        created_at=board.created_at,
        updated_at=board.updated_at,
        current_user_role="owner",
    )


@router.get(
    "",
    response_model=BoardListResponse,
    summary="List all whiteboards for the authenticated user",
)
async def list_boards(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> BoardListResponse:
    """Retrieve paginated non-deleted boards where the authenticated user is a member."""
    rows, total = await list_user_boards(
        session=session,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    items = [
        BoardResponse(
            id=board.id,
            title=board.title,
            owner_id=board.owner_id,
            created_at=board.created_at,
            updated_at=board.updated_at,
            current_user_role=role,
        )
        for board, role in rows
    ]
    return BoardListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{board_id}",
    response_model=BoardResponse,
    summary="Get board metadata by ID",
)
async def get_board(
    membership: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.READ_BOARD)),
    ],
) -> BoardResponse:
    """Fetch board metadata for members with read permissions."""
    board = membership.board
    return BoardResponse(
        id=board.id,
        title=board.title,
        owner_id=board.owner_id,
        created_at=board.created_at,
        updated_at=board.updated_at,
        current_user_role=membership.role,
    )


@router.patch(
    "/{board_id}",
    response_model=BoardResponse,
    summary="Update board title",
)
async def update_board(
    board_id: uuid.UUID,
    payload: BoardUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.UPDATE_METADATA)),
    ],
) -> BoardResponse:
    """Update title for a board (owner-only permission)."""
    board = await update_board_title(session, board_id, payload.title)
    await session.commit()
    return BoardResponse(
        id=board.id,
        title=board.title,
        owner_id=board.owner_id,
        created_at=board.created_at,
        updated_at=board.updated_at,
        current_user_role=membership.role,
    )


@router.delete(
    "/{board_id}",
    response_model=MessageResponse,
    summary="Soft-delete a whiteboard",
)
async def delete_board(
    board_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.DELETE_BOARD)),
    ],
) -> MessageResponse:
    """Soft-delete an active board (owner-only permission)."""
    await soft_delete_board(session, board_id)
    await session.commit()
    return MessageResponse(message=f"Board '{board_id}' has been successfully deleted")


@router.post(
    "/{board_id}/transfer-ownership",
    response_model=BoardResponse,
    summary="Transfer board ownership to another user",
)
async def transfer_board_ownership_endpoint(
    board_id: uuid.UUID,
    payload: TransferOwnershipRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        BoardMember,
        Depends(require_board_permission_dep(BoardPermission.TRANSFER_OWNERSHIP)),
    ],
) -> BoardResponse:
    """Transfer ownership of the board to another active user (owner-only permission)."""
    try:
        board, _ = await transfer_ownership(
            session=session,
            board_id=board_id,
            current_owner_id=current_user.id,
            new_owner_id=payload.new_owner_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return BoardResponse(
        id=board.id,
        title=board.title,
        owner_id=board.owner_id,
        created_at=board.created_at,
        updated_at=board.updated_at,
        current_user_role="editor",
    )
