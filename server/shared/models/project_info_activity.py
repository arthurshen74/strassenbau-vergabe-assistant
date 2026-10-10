from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectInfoActivity(BaseModel):
    """One granular activity line emitted by a worker during a Projektinfo job."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    job_uuid: UUID
    project_uuid: UUID
    worker_id: str
    phase: str | None = None
    message: str
    ts: datetime


class NewProjectInfoActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_uuid: UUID
    project_uuid: UUID
    worker_id: str
    phase: str | None = None
    message: str
