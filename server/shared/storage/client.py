from __future__ import annotations

from uuid import UUID


def raw_key(project_uuid: UUID, document_id: UUID, filename: str) -> str:
    """Object key for an uploaded document. Convention uses `project_uuid` (the surrogate),
    never the external `project_id`. See docs/DATA_MODEL.md §2.3."""
    return f"projects/{project_uuid}/raw/{document_id}/{filename}"


def thumbnail_key(
    project_uuid: UUID, document_id: UUID, page_number: int, ext: str
) -> str:
    return f"projects/{project_uuid}/thumbnails/{document_id}/p{page_number}.{ext}"


class StorageClient:
    """MinIO/S3 object storage over the `settings.s3_bucket` bucket; keys are immutable once
    written. Key conventions are the module-level `raw_key` / `thumbnail_key` helpers. The
    concrete library is `boto3` (S3 API; reaches MinIO via `endpoint_url=settings.s3_endpoint`),
    its sync calls wrapped to satisfy the async interface. See
    docs/DATA_MODEL.md §2.3 and ARCHITECTURE.md "Object Storage Layout".
    """

    async def download(self, key: str) -> bytes:
        raise NotImplementedError

    async def upload(self, key: str, data: bytes, *, content_type: str) -> None:
        raise NotImplementedError
