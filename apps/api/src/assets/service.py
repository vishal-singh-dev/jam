"""Asset lifecycle service for presigned uploads, storage verification, and board attachments."""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import Settings, get_settings
from src.models.asset import Asset, BoardAsset
from src.models.board import Board, BoardMember
from src.storage.base import StorageProvider


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal and remove unsupported characters."""
    base = filename.split("/")[-1].split("\\")[-1]
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    return cleaned or "unnamed_asset"


async def generate_upload_intent(
    session: AsyncSession,
    storage: StorageProvider,
    owner_id: uuid.UUID,
    filename: str,
    content_type: str,
    byte_size: int,
    media_type: str,
    settings: Settings | None = None,
) -> tuple[Asset, str]:
    """Validate file upload policy, generate server-controlled key and presigned PUT URL."""
    cfg = settings or get_settings()

    # Validate file size
    max_bytes = (
        cfg.asset_max_gif_size_bytes
        if media_type == "gif" or content_type == "image/gif"
        else cfg.asset_max_file_size_bytes
    )
    if byte_size > max_bytes:
        raise ValueError(
            f"File size {byte_size} bytes exceeds maximum allowed limit of {max_bytes} bytes"
        )

    asset_id = uuid.uuid4()
    safe_name = sanitize_filename(filename)
    object_key = f"assets/{owner_id}/{asset_id}/{safe_name}"

    upload_url = storage.generate_presigned_put_url(
        object_key=object_key,
        content_type=content_type,
        expires_in=cfg.r2_presigned_url_expire_seconds,
    )

    is_animated = media_type == "gif" or content_type == "image/gif"

    asset = Asset(
        id=asset_id,
        owner_id=owner_id,
        storage_provider="cloudflare_r2",
        bucket_name=cfg.r2_bucket_name,
        object_key=object_key,
        original_filename=safe_name,
        media_type=media_type,
        content_type=content_type,
        byte_size=byte_size,
        is_animated=is_animated,
        status="pending",
    )
    session.add(asset)
    await session.flush()

    return asset, upload_url


async def complete_asset_upload(
    session: AsyncSession,
    storage: StorageProvider,
    asset_id: uuid.UUID,
    owner_id: uuid.UUID,
    width: int | None = None,
    height: int | None = None,
    checksum_sha256: str | None = None,
) -> Asset:
    """Verify that the object was uploaded to storage and mark the asset ready."""
    res = await session.execute(select(Asset).where(Asset.id == asset_id))
    asset = res.scalar_one_or_none()

    if not asset or asset.owner_id != owner_id:
        raise ValueError(f"Asset '{asset_id}' not found or not owned by user")

    if asset.status == "ready":
        return asset

    # Verify object existence in storage
    exists, actual_size, _ = storage.verify_object_exists(asset.object_key)
    if not exists:
        raise ValueError(
            f"Object '{asset.object_key}' was not found in storage. Ensure upload completed."
        )

    if actual_size:
        asset.byte_size = actual_size

    if width is not None:
        asset.width = width
    if height is not None:
        asset.height = height
    if checksum_sha256:
        asset.checksum_sha256 = checksum_sha256

    asset.status = "ready"
    await session.flush()
    return asset


async def get_asset_by_id(
    session: AsyncSession,
    asset_id: uuid.UUID,
) -> Asset | None:
    """Retrieve ready asset by ID."""
    res = await session.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.status == "ready",
        )
    )
    return res.scalar_one_or_none()


async def check_user_asset_access(
    session: AsyncSession,
    asset: Asset,
    user_id: uuid.UUID,
) -> bool:
    """Check if a user is authorized to view or use an asset.

    Allowed if:
    1. User is the asset owner.
    2. Asset is associated with a non-deleted board where the user is an active member.
    """
    if asset.owner_id == user_id:
        return True

    # Check board memberships
    query = (
        select(func.count(BoardAsset.id))
        .join(Board, Board.id == BoardAsset.board_id)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(
            BoardAsset.asset_id == asset.id,
            Board.deleted_at.is_(None),
            BoardMember.user_id == user_id,
        )
    )
    res = await session.execute(query)
    count = res.scalar() or 0
    return count > 0


async def list_user_assets(
    session: AsyncSession,
    owner_id: uuid.UUID,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Asset], int]:
    """Retrieve paginated ready assets owned by a user."""
    base_filter = [
        Asset.owner_id == owner_id,
        Asset.status == "ready",
    ]
    if media_type:
        base_filter.append(Asset.media_type == media_type)

    count_res = await session.execute(select(func.count(Asset.id)).where(*base_filter))
    total = count_res.scalar() or 0

    data_res = await session.execute(
        select(Asset)
        .where(*base_filter)
        .order_by(Asset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(data_res.scalars().all())
    return items, total


async def delete_asset(
    session: AsyncSession,
    storage: StorageProvider,
    asset_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> None:
    """Safely delete an asset from storage and database.

    Rejects deletion with an error if the asset is currently referenced by any board.
    """
    res = await session.execute(select(Asset).where(Asset.id == asset_id))
    asset = res.scalar_one_or_none()
    if not asset or asset.owner_id != owner_id:
        raise ValueError(f"Asset '{asset_id}' not found or not owned by user")

    # Prevent deletion while referenced by boards
    ref_res = await session.execute(
        select(func.count(BoardAsset.id)).where(BoardAsset.asset_id == asset_id)
    )
    ref_count = ref_res.scalar() or 0
    if ref_count > 0:
        raise ValueError(
            f"Cannot delete asset '{asset_id}': it is currently referenced by {ref_count} board(s)"
        )

    # Delete from storage
    storage.delete_object(asset.object_key)

    # Delete from database
    await session.delete(asset)
    await session.flush()


async def attach_asset_to_board(
    session: AsyncSession,
    board_id: uuid.UUID,
    asset_id: uuid.UUID,
    added_by_user_id: uuid.UUID,
) -> BoardAsset:
    """Associate a ready asset with a board."""
    asset = await get_asset_by_id(session, asset_id)
    if not asset:
        raise ValueError(f"Ready asset '{asset_id}' not found")

    has_access = await check_user_asset_access(session, asset, added_by_user_id)
    if not has_access:
        raise ValueError("User does not have access to attach this asset")

    # Check for existing association (idempotency)
    existing_res = await session.execute(
        select(BoardAsset).where(
            BoardAsset.board_id == board_id,
            BoardAsset.asset_id == asset_id,
        )
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        existing.asset = asset
        return existing

    assoc = BoardAsset(
        id=uuid.uuid4(),
        board_id=board_id,
        asset_id=asset_id,
        added_by_user_id=added_by_user_id,
    )
    session.add(assoc)
    await session.flush()
    assoc.asset = asset
    return assoc


async def list_board_assets(
    session: AsyncSession,
    board_id: uuid.UUID,
) -> list[BoardAsset]:
    """Retrieve all assets associated with a board."""
    res = await session.execute(
        select(BoardAsset)
        .where(BoardAsset.board_id == board_id)
        .options(selectinload(BoardAsset.asset))
        .order_by(BoardAsset.created_at.asc())
    )
    return list(res.scalars().all())
