from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import IngestStatus


class IngestJob(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_uuid: UUID
    document_uuid: UUID
    status: IngestStatus
    created_at: datetime
    updated_at: datetime


class NewIngestJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    status: IngestStatus = IngestStatus.QUEUED


class IngestJobStatusRow(BaseModel):
    """A document's job status plus its latest progress event (one row per job)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    job_uuid: UUID
    status: IngestStatus
    latest_event: str | None = None
    latest_phase: str | None = None
    latest_message: str | None = None
    latest_ts: datetime | None = None
