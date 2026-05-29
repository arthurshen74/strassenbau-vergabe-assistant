from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class NewIngestJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    project_document_uuid: UUID
    status: IngestStatus = IngestStatus.QUEUED


class IngestJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingest_job_uuid: UUID
    project_uuid: UUID
    project_document_uuid: UUID
    status: IngestStatus
    created_at: datetime
    updated_at: datetime
