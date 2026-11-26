"""Database transactional invariant operations.

Enforces cross-table referential integrity rules that cannot be handled
by simple single-row SQL check constraints (e.g. board ownership agreement
between boards.owner_id and board_members where role='owner', and last-owner protection).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.authorization.exceptions import (
    AuthorizationError,
)
from src.authorization.policies import validate_owner_count_invariant
from src.authorization.roles import BoardRole
from src.models.board import Board, BoardMember


async def create_board_with_owner_tx(
    session: AsyncSession,
    owner_id: uuid.UUID,
    title: str,
) -> tuple[Board, BoardMember]:
    """Atomically create a board and its corresponding owner membership row.

    Guarantees the invariant: boards.owner_id is always represented as an 'owner'
    in board_members within the same atomic transaction.
    """
    board = Board(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
    )
    session.add(board)
    await session.flush()

    member = BoardMember(
        id=uuid.uuid4(),
        board_id=board.id,
        user_id=owner_id,
        role=BoardRole.OWNER.value,
    )
    session.add(member)
    await session.flush()

    return board, member


async def transfer_board_ownership_tx(
    session: AsyncSession,
    board_id: uuid.UUID,
    current_owner_id: uuid.UUID,
    new_owner_id: uuid.UUID,
) -> tuple[Board, BoardMember]:
    """Atomically transfer board ownership from current owner to a new owner.

    1. Updates boards.owner_id to new_owner_id.
    2. Promotes or creates new_owner membership with role='owner'.
    3. Demotes previous owner's membership to role='editor'.
    """
    # Verify current board
    res = await session.execute(select(Board).where(Board.id == board_id).with_for_update())
    board = res.scalar_one_or_none()
    if not board:
        raise ValueError(f"Board '{board_id}' not found")
    if board.owner_id != current_owner_id:
        raise AuthorizationError(f"User '{current_owner_id}' is not the current board owner")

    # Update board owner
    board.owner_id = new_owner_id

    # Update new owner membership
    new_member_res = await session.execute(
        select(BoardMember)
        .where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == new_owner_id,
        )
        .with_for_update()
    )
    new_member = new_member_res.scalar_one_or_none()
    if new_member:
        new_member.role = BoardRole.OWNER.value
    else:
        new_member = BoardMember(
            id=uuid.uuid4(),
            board_id=board_id,
            user_id=new_owner_id,
            role=BoardRole.OWNER.value,
        )
        session.add(new_member)

    # Demote previous owner to editor
    old_member_res = await session.execute(
        select(BoardMember)
        .where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == current_owner_id,
        )
        .with_for_update()
    )
    old_member = old_member_res.scalar_one_or_none()
    if old_member:
        old_member.role = BoardRole.EDITOR.value

    await session.flush()
    return board, new_member


async def remove_or_demote_member_tx(
    session: AsyncSession,
    board_id: uuid.UUID,
    user_id: uuid.UUID,
    new_role: BoardRole | None = None,  # None indicates complete removal
) -> None:
    """Enforce last-owner protection invariant before removing or demoting a member."""
    # Fetch target member
    target_res = await session.execute(
        select(BoardMember)
        .where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == user_id,
        )
        .with_for_update()
    )
    target_member = target_res.scalar_one_or_none()
    if not target_member:
        raise ValueError(f"Member '{user_id}' not found on board '{board_id}'")

    if target_member.role == BoardRole.OWNER.value:
        # Count total owners
        count_res = await session.execute(
            select(func.count(BoardMember.id)).where(
                BoardMember.board_id == board_id,
                BoardMember.role == BoardRole.OWNER.value,
            )
        )
        owner_count = count_res.scalar() or 0
        validate_owner_count_invariant(
            current_owners_count=owner_count,
            is_removing_or_demoting_owner=True,
            board_id=str(board_id),
        )

    if new_role is None:
        await session.delete(target_member)
    else:
        target_member.role = new_role.value

    await session.flush()
