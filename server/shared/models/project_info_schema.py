"""API schemas for a project's Projektinfo job: the re-run request and the job record
the project page polls."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import IngestStatus, ProjectInfoQuery
from shared.models.project_info_job import ProjectInfoResult


class ProjectInfoRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overwrite: bool = False


class ProjectInfoJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_uuid: UUID
    project_uuid: UUID
    language: str
    overwrite: bool
    status: IngestStatus
    attempts: int
    error: str | None = None
    result: dict[ProjectInfoQuery, ProjectInfoResult] | None = None
    created_at: datetime
    updated_at: datetime
