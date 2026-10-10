from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import IngestStatus, ProjectInfoQuery


class ProjectInfoResult(BaseModel):
    """The outcome of one project-info query: the synthesized value and its evidence,
    or the reason nothing was found (`error` when the query could not run)."""

    model_config = ConfigDict(extra="forbid")

    gefunden: bool
    wert: str | None = None
    konfidenz: float | None = None
    beleg: str | None = None
    query_version: int | None = None
    error: str | None = None


class ProjectInfoJob(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_uuid: UUID
    project_uuid: UUID
    language: str
    overwrite: bool
    status: IngestStatus
    locked_at: datetime | None = None
    locked_by: str | None = None
    attempts: int = 0
    error: str | None = None
    result: dict[ProjectInfoQuery, ProjectInfoResult] | None = None
    created_at: datetime
    updated_at: datetime


class NewProjectInfoJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    language: str
    overwrite: bool = False
