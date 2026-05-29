from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    project_id: str
    project_name: str
    created_at: datetime
    updated_at: datetime


class ProjectCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_name: str
    project_description: str | None = None
    vergabe_stelle: str
    project_start: date | None = None
    project_location: str
