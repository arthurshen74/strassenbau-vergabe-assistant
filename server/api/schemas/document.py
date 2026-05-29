from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentTypeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type_uuid: UUID
    document_type: str
    document_type_description: str | None
    form_type_standard: Literal["HVA StB", "VHB"] | None = None
    form_type_number: int | None = None


class ProjectDocumentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_document_uuid: UUID
    project_uuid: UUID
    document_filename: str
    document_type_uuid: UUID
    document_type: str
    document_description: str | None
    number_of_pages: int | None
    ingested_at: datetime
