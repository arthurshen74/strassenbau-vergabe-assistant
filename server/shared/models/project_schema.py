"""API schemas for the Project resource: Create / Read / Update.

These DTOs are the HTTP boundary contract and are exported to the UI via
scripts/export_schema.py. They mirror the domain model in models/project.py but
form a separate type family.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vergabe_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    project_description: str
    vergabestelle: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_uuid: UUID
    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(default=None, min_length=1)
    project_description: str | None = None
    vergabestelle: str | None = None
