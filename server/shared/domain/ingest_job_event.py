from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestEventType(StrEnum):
    STARTED = "ingest_started"
    PROGRESS = "ingest_progress"
    COMPLETED = "ingest_completed"
    ERROR = "ingest_error"


class NewIngestJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingest_job_uuid: UUID
    event: IngestEventType
    phase: str | None = None
    message: str | None = None


class IngestJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingest_job_event_uuid: UUID
    ingest_job_uuid: UUID
    event: IngestEventType
    phase: str | None
    message: str | None
    ts: datetime
