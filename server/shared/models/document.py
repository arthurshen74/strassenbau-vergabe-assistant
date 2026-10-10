from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import DocumentType, FormRole


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int
    form_role: FormRole | None = None
    form_id: str | None = None
    created_at: datetime
    updated_at: datetime


class NewDocument(BaseModel):
    """Shape required to create a Document. PK and timestamps assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int
    form_role: FormRole | None = None
    form_id: str | None = None
