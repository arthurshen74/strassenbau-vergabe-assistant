from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    """A tender project. `project_name` is the Maßnahme, `vergabe_id` the Vergabenummer,
    `location` the Baustelle; the header fields other than the name are optional because
    they are extracted from the tender documents after ingestion."""

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


class NewProject(BaseModel):
    """Shape required to create a Project. PK and timestamps assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    project_name: str
    massnahmenummer: str | None = None
    vergabe_id: str | None = None
    bauleistung: str | None = None
    vergabestelle: str | None = None
    location: str | None = None
    project_description: str | None = None
