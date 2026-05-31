from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_uuid: UUID
    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
    created_at: datetime
    updated_at: datetime


class NewProject(BaseModel):
    """Shape required to create a Project. PK and timestamps assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
