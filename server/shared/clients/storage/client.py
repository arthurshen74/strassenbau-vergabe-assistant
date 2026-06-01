"""MinIO/S3 object storage client.

Wraps a synchronous boto3 S3 client used for raw uploaded files and per-page
thumbnails. The object-key helpers below are the single source of truth for how
keys are laid out in the bucket; the same helpers feed the ``Thumbnail.object_key``
and raw-file keys persisted in the database, so a layout change happens in one place.
"""

from __future__ import annotations

import logging
from uuid import UUID

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from shared.config import settings

logger = logging.getLogger(__name__)

# Object-key layout. These prefixes are a storage contract: every writer and
# reader of an object key derives it from the helpers below, never an inline literal.
RAW_KEY_PREFIX = "raw"
THUMBNAIL_KEY_PREFIX = "thumbnails"


def raw_object_key(document_uuid: UUID) -> str:
    """Storage key for a document's raw uploaded file."""
    return f"{RAW_KEY_PREFIX}/{document_uuid}"


def thumbnail_object_key(document_uuid: UUID, page_number: int) -> str:
    """Storage key for a single page thumbnail of a document."""
    return f"{THUMBNAIL_KEY_PREFIX}/{document_uuid}/{page_number}"


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

    def presign_put(self, key: str, expires: int, content_type: str | None = None) -> str:
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
