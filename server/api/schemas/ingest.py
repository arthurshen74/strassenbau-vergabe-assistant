from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IngestStatus = Literal["queued", "running", "done", "failed"]


class IngestJobDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingest_job_uuid: UUID
    project_uuid: UUID
    project_document_uuid: UUID
    status: IngestStatus
    created_at: datetime
    updated_at: datetime


class IngestStatusDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IngestStatus
    failing_phase: str | None
    counts: dict[str, int]


class IngestJobEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    message: str
    ts: datetime


class IngestStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_started"]
    ingest_job_uuid: UUID
    project_document_uuid: UUID


class IngestProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_progress"]
    ingest_job_uuid: UUID
    phase: str
    message: str


class IngestCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_completed"]
    ingest_job_uuid: UUID


class IngestError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_error"]
    ingest_job_uuid: UUID
    phase: str | None
    message: str


IngestEvent = Annotated[
    IngestStarted | IngestProgress | IngestCompleted | IngestError,
    Field(discriminator="event"),
]
