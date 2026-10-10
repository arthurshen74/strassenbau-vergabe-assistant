from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import ConsoleJobKind, IngestStatus


class ConsoleJobRow(BaseModel):
    """An ingest-console row: an ingest or Projektinfo job with its project and
    document labels and its latest activity line. Projektinfo rows have no document."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    kind: ConsoleJobKind
    job_uuid: UUID
    project_uuid: UUID
    project_name: str
    document_uuid: UUID | None = None
    file_name: str | None = None
    status: IngestStatus
    attempts: int
    locked_by: str | None = None
    locked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    latest_phase: str | None = None
    latest_message: str | None = None
    latest_ts: datetime | None = None
