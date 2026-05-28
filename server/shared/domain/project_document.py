from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NewProjectDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    document_filename: str
    document_type_uuid: UUID
    document_description: str | None = None
    number_of_pages: int | None = None


class ProjectDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_document_uuid: UUID
    project_uuid: UUID
    document_filename: str
    document_type_uuid: UUID
    document_description: str | None
    number_of_pages: int | None
    ingested_at: datetime
