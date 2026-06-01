"""API schemas for the Document resource: Create / Read.

Mirrors the domain model in models/document.py as a separate boundary type family.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import DocumentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int
