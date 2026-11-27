"""Abstract storage provider interface for object storage (Cloudflare R2 / S3)."""

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Abstract base class defining object storage interactions."""

    @abstractmethod
    def generate_presigned_put_url(
        self,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> str:
        """Generate a presigned PUT URL for direct client-to-storage upload."""
        ...

    @abstractmethod
    def generate_presigned_get_url(
        self,
        object_key: str,
        expires_in: int = 900,
    ) -> str:
        """Generate a presigned GET URL for authorized viewing/download."""
        ...

    @abstractmethod
    def verify_object_exists(
        self,
        object_key: str,
    ) -> tuple[bool, int | None, str | None]:
        """Verify object existence and return (exists, byte_size, content_type)."""
        ...

    @abstractmethod
    def delete_object(
        self,
        object_key: str,
    ) -> bool:
        """Delete an object from storage."""
        ...
