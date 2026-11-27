"""Cloudflare R2 media and asset management router implementing Phase 5 endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.assets.service import (
    check_user_asset_access,
    complete_asset_upload,
    delete_asset,
    generate_upload_intent,
    get_asset_by_id,
    list_user_assets,
)
from src.auth.dependencies import get_current_user
from src.config import Settings, get_settings
from src.db.session import get_db
from src.models.user import User
from src.schemas.assets import (
    AssetCompleteRequest,
    AssetListResponse,
    AssetResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from src.schemas.auth import MessageResponse
from src.storage import StorageProvider, get_storage

router = APIRouter(
    prefix="/assets",
    tags=["Assets"],
)


@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a presigned R2 upload URL",
)
async def request_upload_url(
    payload: UploadUrlRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageProvider, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadUrlResponse:
    """Validate asset policy and return server-controlled object key with presigned PUT URL."""
    try:
        asset, upload_url = await generate_upload_intent(
            session=session,
            storage=storage,
            owner_id=current_user.id,
            filename=payload.filename,
            content_type=payload.content_type,
            byte_size=payload.byte_size,
            media_type=payload.media_type,
            settings=settings,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return UploadUrlResponse(
        asset_id=asset.id,
        upload_url=upload_url,
        object_key=asset.object_key,
        expires_in=settings.r2_presigned_url_expire_seconds,
    )


@router.post(
    "/{asset_id}/complete",
    response_model=AssetResponse,
    summary="Verify upload completion against storage and mark asset ready",
)
async def complete_upload(
    asset_id: uuid.UUID,
    payload: AssetCompleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageProvider, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetResponse:
    """Verify that the object exists in storage and transition status to ready."""
    try:
        asset = await complete_asset_upload(
            session=session,
            storage=storage,
            asset_id=asset_id,
            owner_id=current_user.id,
            width=payload.width,
            height=payload.height,
            checksum_sha256=payload.checksum_sha256,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    url = storage.generate_presigned_get_url(
        asset.object_key,
        expires_in=settings.r2_presigned_url_expire_seconds,
    )

    resp = AssetResponse.model_validate(asset)
    resp.url = url
    return resp


@router.get(
    "",
    response_model=AssetListResponse,
    summary="List ready assets owned by the current user",
)
async def list_assets(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageProvider, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
    media_type: Annotated[str | None, Query(description="Filter by media type")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> AssetListResponse:
    """Retrieve paginated ready assets owned by the caller."""
    items, total = await list_user_assets(
        session=session,
        owner_id=current_user.id,
        media_type=media_type,
        page=page,
        page_size=page_size,
    )

    resp_items: list[AssetResponse] = []
    for asset in items:
        resp = AssetResponse.model_validate(asset)
        resp.url = storage.generate_presigned_get_url(
            asset.object_key,
            expires_in=settings.r2_presigned_url_expire_seconds,
        )
        resp_items.append(resp)

    return AssetListResponse(
        items=resp_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Get asset metadata and presigned access URL",
)
async def get_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageProvider, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetResponse:
    """Retrieve metadata and download/display URL for an authorized asset."""
    asset = await get_asset_by_id(session, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found",
        )

    has_access = await check_user_asset_access(session, asset, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not have permission to view this asset",
        )

    url = storage.generate_presigned_get_url(
        asset.object_key,
        expires_in=settings.r2_presigned_url_expire_seconds,
    )

    resp = AssetResponse.model_validate(asset)
    resp.url = url
    return resp


@router.delete(
    "/{asset_id}",
    response_model=MessageResponse,
    summary="Delete an asset",
)
async def delete_asset_endpoint(
    asset_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageProvider, Depends(get_storage)],
) -> MessageResponse:
    """Safely delete an asset from storage and database. Rejects if referenced by boards."""
    try:
        await delete_asset(
            session=session,
            storage=storage,
            asset_id=asset_id,
            owner_id=current_user.id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        # If referenced by boards, 409 Conflict
        err_msg = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "referenced by" in err_msg.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=err_msg,
        ) from exc

    return MessageResponse(message=f"Asset '{asset_id}' has been successfully deleted")
