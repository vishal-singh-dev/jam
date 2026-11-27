"""Pydantic schemas for asset lifecycle, presigned uploads, and board attachments."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/gif": [".gif"],
}

ALLOWED_MEDIA_TYPES = {"image", "gif", "sticker", "background"}


class UploadUrlRequest(BaseModel):
    """Payload to request a presigned R2 upload PUT URL."""

    filename: str = Field(min_length=1, max_length=255, description="Original filename")
    content_type: str = Field(description="MIME type (JPEG, PNG, WebP, GIF)")
    byte_size: int = Field(gt=0, description="Payload byte size")
    media_type: str = Field(
        default="image",
        description="Category: image, gif, sticker, background",
    )

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        lowered = v.lower().strip()
        if lowered not in ALLOWED_CONTENT_TYPES:
            allowed = sorted(ALLOWED_CONTENT_TYPES.keys())
            raise ValueError(
                f"Unsupported content type '{v}'. Allowed types: {allowed}. SVG is disabled."
            )
        return lowered

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, v: str) -> str:
        lowered = v.lower().strip()
        if lowered not in ALLOWED_MEDIA_TYPES:
            raise ValueError(
                f"Invalid media type '{v}'. Allowed types: {sorted(ALLOWED_MEDIA_TYPES)}"
            )
        return lowered


class UploadUrlResponse(BaseModel):
    """Presigned PUT upload URL details."""

    asset_id: uuid.UUID
    upload_url: str
    object_key: str
    expires_in: int


class AssetCompleteRequest(BaseModel):
    """Payload to complete and verify an asset upload."""

    width: int | None = Field(default=None, gt=0, description="Optional image width")
    height: int | None = Field(default=None, gt=0, description="Optional image height")
    checksum_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="Optional SHA-256 digest of the payload",
    )


class AssetResponse(BaseModel):
    """Asset metadata representation with optional retrieval URL."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    storage_provider: str
    bucket_name: str
    object_key: str
    original_filename: str
    media_type: str
    content_type: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    checksum_sha256: str | None = None
    is_animated: bool
    status: str
    url: str | None = Field(default=None, description="Presigned GET URL or public CDN URL")
    created_at: datetime


class AssetListResponse(BaseModel):
    """Paginated list of assets."""

    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


class BoardAssetAttachRequest(BaseModel):
    """Payload to associate an asset with a board."""

    asset_id: uuid.UUID


class BoardAssetResponse(BaseModel):
    """Association record of an asset attached to a board."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    board_id: uuid.UUID
    asset_id: uuid.UUID
    added_by_user_id: uuid.UUID
    asset: AssetResponse
    created_at: datetime


class BoardAssetListResponse(BaseModel):
    """List of assets attached to a board."""

    items: list[BoardAssetResponse]
    total: int
