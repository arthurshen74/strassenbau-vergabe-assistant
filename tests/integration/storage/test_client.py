from __future__ import annotations

import socket
import uuid

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from shared.clients.storage import (
    StorageClient,
    build_storage_client,
    raw_object_key,
    thumbnail_object_key,
)
from shared.config import settings


def _minio_reachable() -> bool:
    try:
        with socket.create_connection((settings.s3_host, settings.s3_port), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _minio_reachable(),
    reason=f"MinIO not reachable at {settings.s3_endpoint}",
)


@pytest.fixture
def client() -> StorageClient:
    return build_storage_client()


def test_put_get_roundtrip(client: StorageClient) -> None:
    key = raw_object_key(uuid.uuid4())
    data = b"%PDF-1.7 round-trip payload"

    client.put_object(key, data, "application/pdf")

    assert client.get_object(key) == data


def test_thumbnail_roundtrip(client: StorageClient) -> None:
    key = thumbnail_object_key(uuid.uuid4(), page_number=3)
    data = b"\x89PNG\r\n\x1a\n thumbnail bytes"

    client.put_object(key, data, "image/png")

    assert client.get_object(key) == data


def test_presign_get_returns_url(client: StorageClient) -> None:
    key = raw_object_key(uuid.uuid4())

    url = client.presign_get(key, expires=3600)

    assert url.startswith("http")
    assert key in url


def test_delete_objects_removes_keys(client: StorageClient) -> None:
    document_uuid = uuid.uuid4()
    raw = raw_object_key(document_uuid)
    thumb = thumbnail_object_key(document_uuid, page_number=1)
    client.put_object(raw, b"raw", "application/pdf")
    client.put_object(thumb, b"thumb", "image/png")

    client.delete_objects([raw, thumb])

    for key in (raw, thumb):
        with pytest.raises((BotoCoreError, ClientError)):
            client.get_object(key)


def test_delete_objects_absent_key_is_not_an_error(client: StorageClient) -> None:
    # S3 DeleteObjects reports success for keys that do not exist, so delete is idempotent.
    client.delete_objects([raw_object_key(uuid.uuid4())])


def test_delete_objects_empty_is_noop(client: StorageClient) -> None:
    client.delete_objects([])
