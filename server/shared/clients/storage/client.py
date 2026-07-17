"""MinIO/S3 object storage client.

Wraps a synchronous boto3 S3 client used for raw uploaded files and per-page thumbnails.
The object-key helpers below are the single source of truth for how keys are laid out in
the bucket; the same helpers feed the ``Thumbnail.object_key`` and raw-file keys
persisted in the database, so a layout change happens in one place.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from shared.config import settings

logger = logging.getLogger(__name__)

# Object-key layout. These prefixes are a storage contract: every writer and reader of
# an object key derives it from the helpers below, never an inline literal.
RAW_KEY_PREFIX = "raw"
THUMBNAIL_KEY_PREFIX = "thumbnails"
MAP_KEY_PREFIX = "maps"

# S3 caps a single DeleteObjects request at 1000 keys.
DELETE_BATCH_MAX = 1000


def raw_object_key(document_uuid: UUID) -> str:
    """Storage key for a document's raw uploaded file."""
    return f"{RAW_KEY_PREFIX}/{document_uuid}"


def thumbnail_object_key(document_uuid: UUID, page_number: int) -> str:
    """Storage key for a single page thumbnail of a document."""
    return f"{THUMBNAIL_KEY_PREFIX}/{document_uuid}/{page_number}"


def map_object_key(project_uuid: UUID, map_id: str) -> str:
    """Storage key for a rendered static map, addressed by a hash of its request
    params."""
    return f"{MAP_KEY_PREFIX}/{project_uuid}/{map_id}"


class StorageClient:
    """Synchronous object-storage client over a single bucket.

    boto3 is blocking; callers in async contexts should offload these methods to a
    thread.
    """

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError):
            logger.exception("put_object failed: bucket=%s key=%s", self._bucket, key)
            raise

    def delete_objects(self, keys: Sequence[str]) -> None:
        """Delete objects by key, batching to the S3 per-request limit. Deleting an
        absent key is not an error, so this is safe to retry."""
        items = list(keys)
        if not items:
            return
        try:
            for start in range(0, len(items), DELETE_BATCH_MAX):
                batch = items[start : start + DELETE_BATCH_MAX]
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
                )
        except (BotoCoreError, ClientError):
            logger.exception(
                "delete_objects failed: bucket=%s count=%d", self._bucket, len(items)
            )
            raise

    def get_object(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError):
            logger.exception("get_object failed: bucket=%s key=%s", self._bucket, key)
            raise

    def presign_get(self, key: str, expires: int) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires,
            )
        except (BotoCoreError, ClientError):
            logger.exception("presign_get failed: bucket=%s key=%s", self._bucket, key)
            raise

    def presign_put(
        self, key: str, expires: int, content_type: str | None = None
    ) -> str:
        params: dict[str, str] = {"Bucket": self._bucket, "Key": key}
        if content_type is not None:
            params["ContentType"] = content_type
        try:
            return self._client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expires,
            )
        except (BotoCoreError, ClientError):
            logger.exception("presign_put failed: bucket=%s key=%s", self._bucket, key)
            raise


def build_storage_client() -> StorageClient:
    """Construct a StorageClient from application settings."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    return StorageClient(client, settings.s3_bucket)
