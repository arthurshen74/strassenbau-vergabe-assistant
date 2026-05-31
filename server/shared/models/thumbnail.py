from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Thumbnail(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    thumbnail_uuid: UUID
    document_uuid: UUID
    page_number: int
    object_key: str
    bucket: str
    width: int
    height: int
    content_type: str
    created_at: datetime


class NewThumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    page_number: int
    object_key: str
    bucket: str
    width: int
    height: int
    content_type: str
