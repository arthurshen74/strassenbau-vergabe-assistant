"""Per-project ingestion status as a stream of IngestEvent envelopes.

There is no LISTEN/NOTIFY, so the API observes the worker's progress by polling: each tick reads the
ingest_jobs status + the latest ingest_job_event per job for a project, diffs against the last
emitted view, and yields one SSE envelope per changed job. Each job's (status, latest event) maps to
the IngestEvent the UI consumes, keyed by document_uuid. The mapping/diff is pure (`diff_status`) so
it is unit-testable without a database; `stream_project_status` only adds the polling loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.enums import IngestStatus
from shared.models.ingest_job import IngestJobStatusRow
from shared.models.ingest_schema import (
    IngestCompleted,
    IngestError,
    IngestProgress,
    IngestQueued,
    IngestStarted,
)
from shared.models.sse_schema import DATA, EVENT
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.services.ingestion.progress import IngestEvent as IngestEventName

IngestEventModel = (
    IngestQueued | IngestStarted | IngestProgress | IngestCompleted | IngestError
)

# A job's emitted view: a change in (status, latest event ts) triggers a new event.
JobView = tuple[IngestStatus, datetime | None]

# Yielded between events during idle periods; the route renders it as an SSE comment to keep the
# connection alive through proxies.
HEARTBEAT = "heartbeat"
HEARTBEAT_SECONDS = 15.0

_DEFAULT_ERROR_MESSAGE = "ingestion failed"


def _event_for_row(row: IngestJobStatusRow) -> IngestEventModel:
    """Map a job's status + latest event to the IngestEvent the UI renders."""
    if row.status is IngestStatus.QUEUED:
        return IngestQueued(
            event="ingest_queued", job_uuid=row.job_uuid, document_uuid=row.document_uuid
        )
    if row.status is IngestStatus.RUNNING:
        if row.latest_event is None or row.latest_event == IngestEventName.STARTED.value:
            return IngestStarted(
                event="ingest_started", job_uuid=row.job_uuid, document_uuid=row.document_uuid
            )
        return IngestProgress(
            event="ingest_progress",
            job_uuid=row.job_uuid,
            document_uuid=row.document_uuid,
            phase=row.latest_phase or "",
            message=row.latest_message or "",
        )
    if row.status is IngestStatus.DONE:
        return IngestCompleted(
            event="ingest_completed", job_uuid=row.job_uuid, document_uuid=row.document_uuid
        )
    # FAILED: prefer the failure event's phase/message; otherwise a generic reason.
    if row.latest_event == IngestEventName.FAILED.value:
        phase, message = row.latest_phase, row.latest_message or _DEFAULT_ERROR_MESSAGE
    else:
        phase, message = None, _DEFAULT_ERROR_MESSAGE
    return IngestError(
        event="ingest_error",
        job_uuid=row.job_uuid,
        document_uuid=row.document_uuid,
        phase=phase,
        message=message,
    )


def diff_status(
    prev: dict[UUID, JobView], rows: list[IngestJobStatusRow]
) -> tuple[list[dict], dict[UUID, JobView]]:
    """Return (SSE envelopes for jobs whose view changed, the new view state)."""
    events: list[dict] = []
    next_state: dict[UUID, JobView] = {}
    for row in rows:
        view: JobView = (row.status, row.latest_ts)
        next_state[row.job_uuid] = view
        if prev.get(row.job_uuid) == view:
            continue
        payload = _event_for_row(row)
        events.append({EVENT: payload.event, DATA: payload.model_dump(mode="json")})
    return events, next_state


async def stream_project_status(
    engine: AsyncEngine, project_uuid: UUID, *, poll_interval: float
) -> AsyncIterator[dict]:
    """Yield SSE envelopes as the project's ingest jobs change; runs until the caller stops.

    The first tick seeds the current state for every job (so a fresh connection is fully primed),
    then each tick emits only changes. A heartbeat is interleaved during idle periods. Client
    disconnect cancels the sleep, which propagates out and ends the generator."""
    state: dict[UUID, JobView] = {}
    idle = 0.0
    while True:
        async with engine.connect() as conn:
            rows = await IngestJobRepository(conn).status_for_project(project_uuid)
        events, state = diff_status(state, rows)
        if events:
            idle = 0.0
            for event in events:
                yield event
        else:
            idle += poll_interval
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield {HEARTBEAT: True}
        await asyncio.sleep(poll_interval)
