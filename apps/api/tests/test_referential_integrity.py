"""Integration tests for PostgreSQL schema constraints, relationships, and referential integrity."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.authorization.exceptions import LastOwnerProtectionError
from src.authorization.roles import BoardRole
from src.db.invariants import (
    create_board_with_owner_tx,
    remove_or_demote_member_tx,
    transfer_board_ownership_tx,
)
from src.models.asset import Asset, BoardAsset
from src.models.auth import (
    AuthIdentity,
)
from src.models.board import (
    BoardDocument,
    BoardInvitation,
    BoardMember,
    BoardUpdate,
)
from src.models.user import User

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/whiteboard_db"


@pytest.fixture
async def session() -> AsyncSession:
    """Provide an isolated async session for database integrity tests."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as sess:
        yield sess
        await sess.rollback()
    await engine.dispose()


def make_user(prefix: str = "user") -> User:
    """Helper to generate unique user instances."""
    uid = uuid.uuid4()
    return User(
        id=uid,
        display_name=f"{prefix}_{uid.hex[:6]}",
        email=f"{prefix}_{uid.hex[:6]}@example.com",
        normalized_email=f"{prefix}_{uid.hex[:6]}@example.com",
        email_verified=True,
    )


@pytest.mark.asyncio
async def test_duplicate_normalized_email_rejected(session: AsyncSession) -> None:
    """Normalized email must be globally unique across users."""
    u1 = make_user("alice")
    u2 = make_user("bob")
    u2.normalized_email = u1.normalized_email  # Force duplicate normalized email

    session.add(u1)
    await session.flush()

    session.add(u2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_auth_identity_provider_and_credentials_checks(session: AsyncSession) -> None:
    """auth_identities must enforce valid providers and appropriate credentials."""
    user = make_user("ident_test")
    session.add(user)
    await session.flush()

    # 1. Invalid provider (e.g. 'github') rejected by check constraint
    invalid_ident = AuthIdentity(
        user_id=user.id,
        provider="github",
        provider_subject="12345",
    )
    session.add(invalid_ident)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Re-add user after rollback
    user = make_user("ident_test2")
    session.add(user)
    await session.flush()

    # 2. Local provider without password_hash rejected
    local_no_pw = AuthIdentity(
        user_id=user.id,
        provider="local",
        password_hash=None,
    )
    session.add(local_no_pw)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Re-add user after rollback
    user = make_user("ident_test3")
    session.add(user)
    await session.flush()

    # 3. Google provider without provider_subject rejected
    google_no_sub = AuthIdentity(
        user_id=user.id,
        provider="google",
        provider_subject=None,
    )
    session.add(google_no_sub)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_one_local_identity_per_user(session: AsyncSession) -> None:
    """A user can have at most one local auth identity."""
    user = make_user("single_local")
    session.add(user)
    await session.flush()

    ident1 = AuthIdentity(
        user_id=user.id,
        provider="local",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash1",
    )
    ident2 = AuthIdentity(
        user_id=user.id,
        provider="local",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash2",
    )
    session.add(ident1)
    await session.flush()

    session.add(ident2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_google_subject_uniqueness(session: AsyncSession) -> None:
    """Duplicate Google provider subjects across different users must be rejected."""
    u1 = make_user("google_user1")
    u2 = make_user("google_user2")
    session.add_all([u1, u2])
    await session.flush()

    g1 = AuthIdentity(
        user_id=u1.id,
        provider="google",
        provider_subject="sub_1234567890",
    )
    g2 = AuthIdentity(
        user_id=u2.id,
        provider="google",
        provider_subject="sub_1234567890",  # Duplicate subject
    )
    session.add(g1)
    await session.flush()

    session.add(g2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_board_owner_creation_atomic(session: AsyncSession) -> None:
    """Creating a board atomically generates the board and owner membership row."""
    owner = make_user("board_creator")
    session.add(owner)
    await session.flush()

    board, member = await create_board_with_owner_tx(
        session=session,
        owner_id=owner.id,
        title="Sprint Planning Board",
    )

    assert board.id is not None
    assert board.owner_id == owner.id
    assert member.board_id == board.id
    assert member.user_id == owner.id
    assert member.role == BoardRole.OWNER.value


@pytest.mark.asyncio
async def test_board_owner_deletion_restricted(session: AsyncSession) -> None:
    """A user who owns active boards cannot be deleted (FK RESTRICT)."""
    owner = make_user("board_owner_delete")
    session.add(owner)
    await session.flush()

    board, _ = await create_board_with_owner_tx(
        session=session,
        owner_id=owner.id,
        title="Mission Critical Canvas",
    )

    # Attempting to delete the owner user while the board still references them
    await session.delete(owner)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_board_deletion_cascades_to_dependents(session: AsyncSession) -> None:
    """Deleting a board cascades to remove members, document snapshots, updates, and invitations."""
    owner = make_user("cascade_owner")
    editor = make_user("cascade_editor")
    session.add_all([owner, editor])
    await session.flush()

    board, _ = await create_board_with_owner_tx(
        session=session,
        owner_id=owner.id,
        title="Cascade Test Board",
    )

    # Add editor member
    editor_member = BoardMember(
        board_id=board.id,
        user_id=editor.id,
        role=BoardRole.EDITOR.value,
    )
    # Add document snapshot
    doc = BoardDocument(
        board_id=board.id,
        snapshot=b"binary_yjs_snapshot_payload",
        snapshot_version=1,
    )
    # Add update
    update = BoardUpdate(
        board_id=board.id,
        sequence=1,
        update=b"binary_yjs_update_chunk",
    )
    # Add invitation
    invitation = BoardInvitation(
        board_id=board.id,
        invited_email_normalized="invitee@example.com",
        role="editor",
        token_hash=f"hash_{uuid.uuid4().hex}",
        invited_by_user_id=owner.id,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )

    session.add_all([editor_member, doc, update, invitation])
    await session.flush()

    # Now delete the board
    await session.delete(board)
    await session.flush()

    # Verify dependents are deleted
    members_q = select(BoardMember).where(BoardMember.board_id == board.id)
    assert (await session.execute(members_q)).scalars().all() == []

    doc_q = select(BoardDocument).where(BoardDocument.board_id == board.id)
    assert (await session.execute(doc_q)).scalar_one_or_none() is None

    updates_q = select(BoardUpdate).where(BoardUpdate.board_id == board.id)
    assert (await session.execute(updates_q)).scalars().all() == []

    invites_q = select(BoardInvitation).where(BoardInvitation.board_id == board.id)
    assert (await session.execute(invites_q)).scalars().all() == []


@pytest.mark.asyncio
async def test_board_member_uniqueness_and_role_constraints(session: AsyncSession) -> None:
    """Board member must have a valid role and duplicate memberships are rejected."""
    owner = make_user("bm_owner")
    user = make_user("bm_user")
    session.add_all([owner, user])
    await session.flush()

    board, _ = await create_board_with_owner_tx(session, owner.id, "Membership Constraints Board")

    # 1. Invalid role check constraint
    invalid_member = BoardMember(
        board_id=board.id,
        user_id=user.id,
        role="superuser",  # Invalid role
    )
    session.add(invalid_member)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Re-fetch after rollback
    owner = make_user("bm_owner2")
    user = make_user("bm_user2")
    session.add_all([owner, user])
    await session.flush()
    board, _ = await create_board_with_owner_tx(session, owner.id, "Membership Constraints Board 2")

    # 2. Duplicate membership constraint
    m1 = BoardMember(board_id=board.id, user_id=user.id, role=BoardRole.VIEWER.value)
    m2 = BoardMember(board_id=board.id, user_id=user.id, role=BoardRole.EDITOR.value)
    session.add(m1)
    await session.flush()

    session.add(m2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_board_ownership_transfer_atomic(session: AsyncSession) -> None:
    """Ownership transfer updates owner_id, promotes new owner, and demotes previous owner."""
    owner1 = make_user("transfer_owner1")
    owner2 = make_user("transfer_owner2")
    session.add_all([owner1, owner2])
    await session.flush()

    board, _ = await create_board_with_owner_tx(session, owner1.id, "Transfer Board")

    # Transfer ownership to owner2
    updated_board, new_member = await transfer_board_ownership_tx(
        session=session,
        board_id=board.id,
        current_owner_id=owner1.id,
        new_owner_id=owner2.id,
    )

    assert updated_board.owner_id == owner2.id
    assert new_member.user_id == owner2.id
    assert new_member.role == BoardRole.OWNER.value

    # Verify owner1 was demoted to editor
    old_member_res = await session.execute(
        select(BoardMember).where(
            BoardMember.board_id == board.id,
            BoardMember.user_id == owner1.id,
        )
    )
    old_member = old_member_res.scalar_one()
    assert old_member.role == BoardRole.EDITOR.value


@pytest.mark.asyncio
async def test_last_owner_protection_in_service(session: AsyncSession) -> None:
    """Cannot remove or demote the sole owner of a board."""
    owner = make_user("sole_owner")
    session.add(owner)
    await session.flush()

    board, _ = await create_board_with_owner_tx(session, owner.id, "Protected Board")

    # Attempting to remove the sole owner raises LastOwnerProtectionError
    with pytest.raises(LastOwnerProtectionError):
        await remove_or_demote_member_tx(
            session=session,
            board_id=board.id,
            user_id=owner.id,
            new_role=None,  # Complete removal
        )

    # Attempting to demote the sole owner raises LastOwnerProtectionError
    with pytest.raises(LastOwnerProtectionError):
        await remove_or_demote_member_tx(
            session=session,
            board_id=board.id,
            user_id=owner.id,
            new_role=BoardRole.EDITOR,  # Demotion
        )


@pytest.mark.asyncio
async def test_asset_check_constraints_and_uniqueness(session: AsyncSession) -> None:
    """Asset checks enforce media_type, positive byte size, and unique object key."""
    owner = make_user("asset_owner")
    session.add(owner)
    await session.flush()

    # 1. Invalid media_type rejected
    invalid_media = Asset(
        owner_id=owner.id,
        storage_provider="cloudflare_r2",
        bucket_name="assets-bucket",
        object_key="key_1",
        original_filename="video.mp4",
        media_type="video",  # Invalid
        content_type="video/mp4",
        byte_size=1024,
    )
    session.add(invalid_media)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Re-fetch after rollback
    owner = make_user("asset_owner2")
    session.add(owner)
    await session.flush()

    # 2. Negative or zero byte size rejected
    zero_bytes = Asset(
        owner_id=owner.id,
        storage_provider="cloudflare_r2",
        bucket_name="assets-bucket",
        object_key="key_zero",
        original_filename="empty.png",
        media_type="image",
        content_type="image/png",
        byte_size=0,  # Invalid
    )
    session.add(zero_bytes)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Re-fetch after rollback
    owner = make_user("asset_owner3")
    session.add(owner)
    await session.flush()

    # 3. Duplicate object key on same provider/bucket rejected
    a1 = Asset(
        owner_id=owner.id,
        storage_provider="cloudflare_r2",
        bucket_name="assets-bucket",
        object_key="shared_key_1",
        original_filename="img1.png",
        media_type="image",
        content_type="image/png",
        byte_size=2048,
    )
    a2 = Asset(
        owner_id=owner.id,
        storage_provider="cloudflare_r2",
        bucket_name="assets-bucket",
        object_key="shared_key_1",  # Duplicate key
        original_filename="img2.png",
        media_type="image",
        content_type="image/png",
        byte_size=4096,
    )
    session.add(a1)
    await session.flush()

    session.add(a2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_asset_deletion_restricted_when_in_board_assets(session: AsyncSession) -> None:
    """An asset referenced by board_assets cannot be deleted (FK RESTRICT)."""
    user = make_user("board_asset_user")
    session.add(user)
    await session.flush()

    board, _ = await create_board_with_owner_tx(session, user.id, "Asset Association Board")

    asset = Asset(
        owner_id=user.id,
        storage_provider="cloudflare_r2",
        bucket_name="assets-bucket",
        object_key=f"asset_{uuid.uuid4().hex}.png",
        original_filename="diagram.png",
        media_type="image",
        content_type="image/png",
        byte_size=10240,
    )
    session.add(asset)
    await session.flush()

    board_asset = BoardAsset(
        board_id=board.id,
        asset_id=asset.id,
        added_by_user_id=user.id,
    )
    session.add(board_asset)
    await session.flush()

    # Attempting to delete the asset directly while board_assets references it must fail
    await session.delete(asset)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_board_updates_sequence_uniqueness(session: AsyncSession) -> None:
    """Duplicate sequence numbers on the same board must be rejected."""
    owner = make_user("seq_owner")
    session.add(owner)
    await session.flush()

    board, _ = await create_board_with_owner_tx(session, owner.id, "Sequence Board")

    u1 = BoardUpdate(board_id=board.id, sequence=1, update=b"chunk1")
    u2 = BoardUpdate(board_id=board.id, sequence=1, update=b"chunk2")  # Duplicate sequence 1

    session.add(u1)
    await session.flush()

    session.add(u2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
