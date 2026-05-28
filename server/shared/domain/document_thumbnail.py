from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NewDocumentThumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_document_uuid: UUID
    page_number: int
    object_key: str
    bucket: str
    width: int
    height: int
    content_type: str


class DocumentThumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thumbnail_uuid: UUID
    project_document_uuid: UUID
    page_number: int
    object_key: str
    bucket: str
    width: int
    height: int
    content_type: str
    created_at: datetime
