"""Storage package providing object storage abstractions and implementations."""

from typing import Annotated

from fastapi import Depends

from src.config import Settings, get_settings
from src.storage.base import StorageProvider
from src.storage.mock import MockStorageProvider
from src.storage.r2 import CloudflareR2Storage

_mock_storage: MockStorageProvider | None = None
_r2_storage: CloudflareR2Storage | None = None


def get_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StorageProvider:
    """Retrieve storage provider instance based on environment configuration."""
    global _mock_storage, _r2_storage

    # If test environment or placeholder credentials, use MockStorageProvider
    if (
        settings.environment == "testing"
        or not settings.r2_access_key_id
        or settings.r2_access_key_id == "placeholder-access-key-id"
    ):
        if _mock_storage is None:
            _mock_storage = MockStorageProvider(bucket_name=settings.r2_bucket_name)
        return _mock_storage

    if _r2_storage is None:
        _r2_storage = CloudflareR2Storage(settings=settings)
    return _r2_storage


__all__ = [
    "CloudflareR2Storage",
    "MockStorageProvider",
    "StorageProvider",
    "get_storage",
]
