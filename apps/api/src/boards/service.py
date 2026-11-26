"""Board management domain service: CRUD, memberships, and ownership lifecycle."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.authorization.roles import BoardRole
from src.db.invariants import (
    create_board_with_owner_tx,
    remove_or_demote_member_tx,
    transfer_board_ownership_tx,
)
from src.models.board import Board, BoardMember
from src.models.user import User


async def create_board(
    session: AsyncSession,
    owner_id: uuid.UUID,
    title: str,
) -> Board:
    """Create a new board and its atomic owner membership row."""
    board, _ = await create_board_with_owner_tx(
        session=session,
        owner_id=owner_id,
        title=title.strip(),
    )
    return board


async def list_user_boards(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Board, str]], int]:
    """Retrieve paginated non-deleted boards where user is a member with role."""
    base_filter = (
        BoardMember.user_id == user_id,
        Board.deleted_at.is_(None),
    )

    # 1. Total matching count
    count_query = (
        select(func.count(Board.id))
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(*base_filter)
    )
    total_res = await session.execute(count_query)
    total = total_res.scalar() or 0

    # 2. Paginated rows with role
    data_query = (
        select(Board, BoardMember.role)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(*base_filter)
        .order_by(Board.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await session.execute(data_query)
    rows = list(res.all())
    return rows, total


async def get_board_by_id(
    session: AsyncSession,
    board_id: uuid.UUID,
) -> Board | None:
    """Fetch an active non-deleted board by ID."""
    res = await session.execute(
        select(Board).where(
            Board.id == board_id,
            Board.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def update_board_title(
    session: AsyncSession,
    board_id: uuid.UUID,
    title: str,
) -> Board:
    """Update title for a non-deleted board."""
    board = await get_board_by_id(session, board_id)
    if not board:
        raise ValueError(f"Board '{board_id}' not found")

    board.title = title.strip()
    board.updated_at = datetime.now(UTC)
    await session.flush()
    return board


async def soft_delete_board(
    session: AsyncSession,
    board_id: uuid.UUID,
) -> None:
    """Mark a board as soft-deleted."""
    board = await get_board_by_id(session, board_id)
    if not board:
        raise ValueError(f"Board '{board_id}' not found")

    board.deleted_at = datetime.now(UTC)
    await session.flush()


async def list_board_members(
    session: AsyncSession,
    board_id: uuid.UUID,
) -> list[BoardMember]:
    """List all members of a board ordered by creation time."""
    res = await session.execute(
        select(BoardMember)
        .where(BoardMember.board_id == board_id)
        .options(selectinload(BoardMember.user))
        .order_by(BoardMember.created_at.asc())
    )
    return list(res.scalars().all())


async def add_board_member(
    session: AsyncSession,
    board_id: uuid.UUID,
    target_user: User,
    role: BoardRole,
) -> BoardMember:
    """Add a new member to a board. Rejects duplicates and direct owner addition."""
    if role == BoardRole.OWNER:
        raise ValueError(
            "Cannot add a member as 'owner' directly. Use the transfer ownership operation instead."
        )

    # Check for existing membership
    existing_res = await session.execute(
        select(BoardMember).where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == target_user.id,
        )
    )
    if existing_res.scalar_one_or_none():
        raise ValueError(
            f"User '{target_user.display_name}' ({target_user.email}) is already a member"
        )

    member = BoardMember(
        id=uuid.uuid4(),
        board_id=board_id,
        user_id=target_user.id,
        role=role.value,
    )
    session.add(member)
    await session.flush()

    # Preload user relationship
    member.user = target_user
    return member


async def update_member_role(
    session: AsyncSession,
    board_id: uuid.UUID,
    current_owner_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: BoardRole,
) -> BoardMember:
    """Update a member's role or transfer ownership if new_role='owner'."""
    if new_role == BoardRole.OWNER:
        _, new_owner_member = await transfer_board_ownership_tx(
            session=session,
            board_id=board_id,
            current_owner_id=current_owner_id,
            new_owner_id=target_user_id,
        )
        # Reload with user relationship
        res = await session.execute(
            select(BoardMember)
            .where(BoardMember.id == new_owner_member.id)
            .options(selectinload(BoardMember.user))
        )
        return res.scalar_one()

    # Demote or change role
    await remove_or_demote_member_tx(
        session=session,
        board_id=board_id,
        user_id=target_user_id,
        new_role=new_role,
    )

    res = await session.execute(
        select(BoardMember)
        .where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == target_user_id,
        )
        .options(selectinload(BoardMember.user))
    )
    return res.scalar_one()


async def remove_member(
    session: AsyncSession,
    board_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> None:
    """Remove a member from a board with last-owner protection."""
    await remove_or_demote_member_tx(
        session=session,
        board_id=board_id,
        user_id=target_user_id,
        new_role=None,
    )


async def transfer_ownership(
    session: AsyncSession,
    board_id: uuid.UUID,
    current_owner_id: uuid.UUID,
    new_owner_id: uuid.UUID,
) -> tuple[Board, BoardMember]:
    """Explicitly transfer board ownership to a different user."""
    if current_owner_id == new_owner_id:
        raise ValueError("Cannot transfer ownership to yourself")

    # Verify new owner user exists
    user_res = await session.execute(
        select(User).where(User.id == new_owner_id, User.is_active.is_(True))
    )
    if not user_res.scalar_one_or_none():
        raise ValueError(f"Target user '{new_owner_id}' not found or inactive")

    board, new_owner_member = await transfer_board_ownership_tx(
        session=session,
        board_id=board_id,
        current_owner_id=current_owner_id,
        new_owner_id=new_owner_id,
    )
    return board, new_owner_member
