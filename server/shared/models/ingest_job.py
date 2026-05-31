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
