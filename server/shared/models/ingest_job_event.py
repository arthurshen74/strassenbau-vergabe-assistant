from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestJobEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_event_uuid: UUID
    job_uuid: UUID
    event: str
    pipeline_phase: str | None = None
    message: str
    ts: datetime


class NewIngestJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_uuid: UUID
    event: str
    pipeline_phase: str | None = None
    message: str
