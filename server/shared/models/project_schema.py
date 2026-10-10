"""API schemas for the Project resource: Create / Read / Update, and the result of
creating a project from a ZIP.

These DTOs are the HTTP boundary contract and are exported to the UI via
scripts/export_schema.py. They mirror the domain model in models/project.py but form a
separate type family.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.document_schema import DocumentRead


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(min_length=1)
    massnahmenummer: str | None = None
    vergabe_id: str | None = None
    bauleistung: str | None = None
    vergabestelle: str | None = None
    location: str | None = None
    project_description: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_uuid: UUID
    project_name: str
    massnahmenummer: str | None = None
    vergabe_id: str | None = None
    bauleistung: str | None = None
    vergabestelle: str | None = None
    location: str | None = None
    project_description: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    """Partial update: only fields present in the request body change; an explicit null
    clears an optional field."""

    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(default=None, min_length=1)
    massnahmenummer: str | None = None
    vergabe_id: str | None = None
    bauleistung: str | None = None
    vergabestelle: str | None = None
    location: str | None = None
    project_description: str | None = None


class ProjectFromZipResult(BaseModel):
    """A project created from one ZIP: the project, its queued documents, and the ZIP
    entry paths that were not ingested."""

    model_config = ConfigDict(extra="forbid")

    project: ProjectRead
    documents: list[DocumentRead]
    skipped: list[str]
