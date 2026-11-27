"""In-memory mock storage provider for unit and integration testing."""

from dataclasses import dataclass

from src.storage.base import StorageProvider


@dataclass
class MockStoredObject:
    """Mock stored object metadata."""

    size: int
    content_type: str


class MockStorageProvider(StorageProvider):
    """In-memory storage provider that simulates S3/R2 operations."""

    def __init__(self, bucket_name: str = "mock-bucket") -> None:
        self.bucket = bucket_name
        self.objects: dict[str, MockStoredObject] = {}

    def set_mock_object(self, object_key: str, size: int, content_type: str) -> None:
        """Helper to seed an object into the mock storage."""
        self.objects[object_key] = MockStoredObject(size=size, content_type=content_type)

    def generate_presigned_put_url(
        self,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> str:
        return f"https://mock-r2.local/{self.bucket}/{object_key}?put=true&exp={expires_in}"

    def generate_presigned_get_url(
        self,
        object_key: str,
        expires_in: int = 900,
    ) -> str:
        return f"https://mock-r2.local/{self.bucket}/{object_key}?get=true&exp={expires_in}"

    def verify_object_exists(
        self,
        object_key: str,
    ) -> tuple[bool, int | None, str | None]:
        if object_key in self.objects:
            obj = self.objects[object_key]
            return True, obj.size, obj.content_type
        return False, None, None

    def delete_object(
        self,
        object_key: str,
    ) -> bool:
        if object_key in self.objects:
            del self.objects[object_key]
            return True
        return True
