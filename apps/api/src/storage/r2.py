"""Cloudflare R2 storage provider implementation using boto3 (S3-compatible)."""

import logging
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from src.config import Settings
from src.storage.base import StorageProvider

logger = logging.getLogger("api.storage.r2")


class CloudflareR2Storage(StorageProvider):
    """S3-compatible storage adapter for Cloudflare R2."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = settings.r2_bucket_name
        self.public_url = settings.r2_public_url

        endpoint = settings.r2_endpoint_url
        if not endpoint and settings.r2_account_id:
            endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"

        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.r2_access_key_id or "dummy-access-key",
            aws_secret_access_key=settings.r2_secret_access_key or "dummy-secret-key",
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def generate_presigned_put_url(
        self,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> str:
        """Generate a presigned PUT URL for browser direct upload."""
        url: str = self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url

    def generate_presigned_get_url(
        self,
        object_key: str,
        expires_in: int = 900,
    ) -> str:
        """Generate a presigned GET URL or return public URL if configured."""
        if self.public_url:
            return f"{self.public_url.rstrip('/')}/{object_key}"

        url: str = self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
            },
            ExpiresIn=expires_in,
        )
        return url

    def verify_object_exists(
        self,
        object_key: str,
    ) -> tuple[bool, int | None, str | None]:
        """Check if an object exists in R2 and retrieve its size and content type."""
        try:
            res = self.client.head_object(Bucket=self.bucket, Key=object_key)
            size = res.get("ContentLength")
            content_type = res.get("ContentType")
            return True, size, content_type
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False, None, None
            logger.warning("Error checking object %s in R2: %s", object_key, exc)
            return False, None, None

    def delete_object(
        self,
        object_key: str,
    ) -> bool:
        """Delete an object from R2."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
            return True
        except ClientError as exc:
            logger.error("Failed to delete object %s from R2: %s", object_key, exc)
            return False
