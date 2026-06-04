from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestionActivity(BaseModel):
    """One granular activity line emitted by a worker during ingestion."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    job_uuid: UUID
    document_uuid: UUID
    worker_id: str
    phase: str | None = None
    message: str
    ts: datetime


class NewIngestionActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_uuid: UUID
    document_uuid: UUID
    worker_id: str
    phase: str | None = None
    message: str
