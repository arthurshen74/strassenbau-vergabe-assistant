"""API schemas for ingestion: job/event reads, a status snapshot, and the SSE
event payloads.

The `Read` DTOs mirror models/ingest_job.py and models/ingest_job_event.py.
`IngestStatusRead` is a derived snapshot with no single domain model behind it.
The SSE payloads form the `IngestEvent` discriminated union streamed to the UI;
scripts/export_schema.py emits the union from the pinned members.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import IngestStatus


class IngestJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_uuid: UUID
    document_uuid: UUID
    status: IngestStatus
    created_at: datetime
    updated_at: datetime


class IngestJobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_event_uuid: UUID
    job_uuid: UUID
    event: str
    pipeline_phase: str | None = None
    message: str
    ts: datetime


class IngestStatusRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IngestStatus
    failing_phase: str | None
    counts: dict[str, int]


class IngestStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_started"]
    job_uuid: UUID
    document_uuid: UUID


class IngestProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_progress"]
    job_uuid: UUID
    phase: str
    message: str


class IngestCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_completed"]
    job_uuid: UUID


class IngestError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ingest_error"]
    job_uuid: UUID
    phase: str | None
    message: str


IngestEvent = Annotated[
    IngestStarted | IngestProgress | IngestCompleted | IngestError,
    Field(discriminator="event"),
]
