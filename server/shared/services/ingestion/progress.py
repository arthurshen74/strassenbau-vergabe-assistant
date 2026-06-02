"""Ingest-job progress.

Two complementary emitters for one pipeline milestone: `log_progress` writes a line to the
module logger (which a harness routes to stdout), and `record_event` persists an
IngestJobEvent. Logging always happens; persistence is a no-op when the pipeline runs jobless
(no job_uuid, e.g. in isolated tests or the dev script)."""

from __future__ import annotations

import logging
from enum import StrEnum
from uuid import UUID

from shared.models.ingest_job_event import NewIngestJobEvent
from shared.repositories.ingest_job_events import IngestJobEventRepository

logger = logging.getLogger(__name__)


class IngestPhase(StrEnum):
    INGEST = "ingest"
    EXTRACT = "extract"
    THUMBNAILS = "thumbnails"
    CHUNK = "chunk"
    LV = "lv"


class IngestEvent(StrEnum):
    STARTED = "started"
    SOURCE_LINES_PERSISTED = "source_lines_persisted"
    THUMBNAILS_GENERATED = "thumbnails_generated"
    DOCUMENT_CHUNKS_INDEXED = "document_chunks_indexed"
    LV_ITEMS_INDEXED = "lv_items_indexed"
    COMPLETED = "completed"


def log_progress(*, event: IngestEvent, phase: IngestPhase, message: str) -> None:
    """Emit a progress line to the module logger; a harness routes this logger to stdout."""
    logger.info("[ingest:%s] %s - %s", phase.value, event.value, message)


async def record_event(
    events: IngestJobEventRepository,
    job_uuid: UUID | None,
    *,
    event: IngestEvent,
    phase: IngestPhase,
    message: str,
) -> None:
    """Append one progress event for the job; no-op when running jobless."""
    if job_uuid is None:
        return
    await events.add(
        NewIngestJobEvent(
            job_uuid=job_uuid,
            event=event.value,
            pipeline_phase=phase.value,
            message=message,
        )
    )
