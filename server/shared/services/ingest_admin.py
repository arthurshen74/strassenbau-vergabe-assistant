"""Ops-console operations over ingest and Projektinfo jobs (Option D of the
crash-recovery design).

Lists both job kinds as one list of console rows, requeues a stuck/failed job in place
(reset to QUEUED so the worker reprocesses it -- ingestion is idempotent), and tails a
job's granular activity as SSE. There is no LISTEN/NOTIFY, so every stream here polls
the database server-side like status_stream: the activity streams follow the activity
log by an id cursor until the job is terminal and drained; the console list stream
re-runs the list each tick and emits a full snapshot only when its fingerprint
(`diff_console_jobs`, pure) changed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.console_job import ConsoleJobRow
from shared.models.enums import ConsoleJobKind, IngestStatus
from shared.models.ingest_job import IngestJob
from shared.models.ingest_schema import (
    ConsoleJobRead,
    ConsoleJobsSnapshot,
    IngestActivityLine,
    ProjectInfoActivityLine,
)
from shared.models.project_info_job import ProjectInfoJob
from shared.models.sse_schema import DATA, EVENT
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.repositories.project_info_activity import (
    ProjectInfoActivityLogRepository,
)
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.services.ingestion.status_stream import HEARTBEAT, HEARTBEAT_SECONDS

# Rows read per poll tick; a full batch means a backlog remains and is drained without
# waiting.
ACTIVITY_TAIL_LIMIT = 500

# "Active" console view: open jobs plus jobs finished within this window, so a job
# the user just watched finish does not vanish.
CONSOLE_RECENT_MINUTES = 15

_TERMINAL = (IngestStatus.DONE, IngestStatus.FAILED)

# What makes a console row "changed"; latest_ts moves with every new activity line.
RowFingerprint = tuple[
    ConsoleJobKind, UUID, IngestStatus, int, str | None, datetime | None
]
Fingerprint = tuple[RowFingerprint, ...]


class IngestAdminService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_jobs(
        self,
        *,
        statuses: Sequence[IngestStatus] | None = None,
        project_uuid: UUID | None = None,
        active: bool = False,
    ) -> list[ConsoleJobRow]:
        """Ingest and Projektinfo jobs merged, newest first. `active` keeps open jobs
        and jobs updated within CONSOLE_RECENT_MINUTES."""
        recent_minutes = CONSOLE_RECENT_MINUTES if active else None
        async with self._engine.connect() as conn:
            ingest = await IngestJobRepository(conn).list_for_console(
                statuses=statuses,
                project_uuid=project_uuid,
                recent_minutes=recent_minutes,
            )
            project_info = await ProjectInfoJobRepository(conn).list_for_console(
                statuses=statuses,
                project_uuid=project_uuid,
                recent_minutes=recent_minutes,
            )
        return sorted(ingest + project_info, key=lambda r: r.created_at, reverse=True)

    async def requeue(self, job_uuid: UUID) -> IngestJob | None:
        async with self._engine.begin() as conn:
            return await IngestJobRepository(conn).requeue(job_uuid)

    async def requeue_project_info(self, job_uuid: UUID) -> ProjectInfoJob | None:
        async with self._engine.begin() as conn:
            return await ProjectInfoJobRepository(conn).requeue(job_uuid)


def diff_console_jobs(
    prev: Fingerprint | None, rows: list[ConsoleJobRow]
) -> tuple[dict | None, Fingerprint]:
    """Return (a snapshot SSE envelope if the list changed since `prev`, else None;
    the new fingerprint). `prev=None` (first tick) always emits."""
    fingerprint: Fingerprint = tuple(
        (r.kind, r.job_uuid, r.status, r.attempts, r.locked_by, r.latest_ts)
        for r in rows
    )
    if fingerprint == prev:
        return None, fingerprint
    payload = ConsoleJobsSnapshot(
        event="console_jobs",
        jobs=[ConsoleJobRead.model_validate(r) for r in rows],
    )
    return {EVENT: payload.event, DATA: payload.model_dump(mode="json")}, fingerprint


async def stream_console_jobs(
    engine: AsyncEngine,
    *,
    statuses: Sequence[IngestStatus] | None,
    project_uuid: UUID | None,
    active: bool,
    poll_interval: float,
) -> AsyncIterator[dict]:
    """Yield a full console snapshot whenever the filtered list changes; runs until the
    caller stops. The first tick always emits; a heartbeat is interleaved while
    nothing changes. Client disconnect cancels the sleep and ends the generator."""
    service = IngestAdminService(engine)
    fingerprint: Fingerprint | None = None
    idle = 0.0
    while True:
        rows = await service.list_jobs(
            statuses=statuses, project_uuid=project_uuid, active=active
        )
        event, fingerprint = diff_console_jobs(fingerprint, rows)
        if event is not None:
            idle = 0.0
            yield event
        else:
            idle += poll_interval
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield {HEARTBEAT: True}
        await asyncio.sleep(poll_interval)


async def stream_job_activity(
    engine: AsyncEngine, job_uuid: UUID, *, poll_interval: float
) -> AsyncIterator[dict]:
    """Yield SSE envelopes for a job's activity, oldest first, until it is terminal and
    drained.

    Each tick reads activity past the last id and the job's current status from a fresh
    connection (mirroring status_stream's polling). A heartbeat is interleaved while a
    still-running job is quiet; client disconnect cancels the sleep and ends the
    generator."""
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


async def stream_project_info_activity(
    engine: AsyncEngine, job_uuid: UUID, *, poll_interval: float
) -> AsyncIterator[dict]:
    """stream_job_activity over a Projektinfo job's activity log."""
    after_id = 0
    idle = 0.0
    while True:
        async with engine.connect() as conn:
            rows = await ProjectInfoActivityLogRepository(conn).tail(
                job_uuid, after_id, ACTIVITY_TAIL_LIMIT
            )
            job = await ProjectInfoJobRepository(conn).get(job_uuid)
        if rows:
            idle = 0.0
            for row in rows:
                after_id = row.id
                payload = ProjectInfoActivityLine(
                    event="project_info_activity",
                    id=row.id,
                    job_uuid=row.job_uuid,
                    project_uuid=row.project_uuid,
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
