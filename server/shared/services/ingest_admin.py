"""Ops-console operations over ingest jobs (Option D of the crash-recovery design).

Lists jobs by status, requeues a stuck/failed job in place (reset to QUEUED so the worker
reprocesses it -- ingestion is idempotent), and tails a job's granular activity as SSE. The
activity stream mirrors status_stream: there is no LISTEN/NOTIFY, so it polls the activity log by
an id cursor, emitting new lines until the job is terminal and drained.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.enums import IngestStatus
from shared.models.ingest_job import IngestJob, IngestJobConsoleRow
from shared.models.ingest_schema import IngestActivityLine
from shared.models.sse_schema import DATA, EVENT
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.services.ingestion.status_stream import HEARTBEAT, HEARTBEAT_SECONDS

# Rows read per poll tick; a full batch means a backlog remains and is drained without waiting.
ACTIVITY_TAIL_LIMIT = 500

_TERMINAL = (IngestStatus.DONE, IngestStatus.FAILED)


class IngestAdminService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_jobs(
        self,
        *,
        statuses: Sequence[IngestStatus] | None = None,
        project_uuid: UUID | None = None,
    ) -> list[IngestJobConsoleRow]:
        async with self._engine.connect() as conn:
            return await IngestJobRepository(conn).list_for_console(
                statuses=statuses, project_uuid=project_uuid
            )

    async def requeue(self, job_uuid: UUID) -> IngestJob | None:
        async with self._engine.begin() as conn:
            return await IngestJobRepository(conn).requeue(job_uuid)


async def stream_job_activity(
    engine: AsyncEngine, job_uuid: UUID, *, poll_interval: float
) -> AsyncIterator[dict]:
    """Yield SSE envelopes for a job's activity, oldest first, until it is terminal and drained.

    Each tick reads activity past the last id and the job's current status from a fresh connection
    (mirroring status_stream's polling). A heartbeat is interleaved while a still-running job is
    quiet; client disconnect cancels the sleep and ends the generator."""
    after_id = 0
    idle = 0.0
    while True:
        async with engine.connect() as conn:
            rows = await IngestionActivityLogRepository(conn).tail(
                job_uuid, after_id, ACTIVITY_TAIL_LIMIT
            )
            job = await IngestJobRepository(conn).get(job_uuid)
        if rows:
            idle = 0.0
            for row in rows:
                after_id = row.id
                payload = IngestActivityLine(
                    event="ingest_activity",
                    id=row.id,
                    job_uuid=row.job_uuid,
                    document_uuid=row.document_uuid,
                    worker_id=row.worker_id,
                    phase=row.phase,
                    message=row.message,
                    ts=row.ts,
                )
                yield {EVENT: payload.event, DATA: payload.model_dump(mode="json")}
            if len(rows) == ACTIVITY_TAIL_LIMIT:
                continue  # full batch: a backlog remains, drain it without waiting
            await asyncio.sleep(poll_interval)
            continue
        # No new activity: a finished job is fully drained, so end the stream.
        if job is None or job.status in _TERMINAL:
            return
        idle += poll_interval
        if idle >= HEARTBEAT_SECONDS:
            idle = 0.0
            yield {HEARTBEAT: True}
        await asyncio.sleep(poll_interval)
