"""Buffered writer for the granular ingestion activity stream.

A worker opens one ActivityWriter per job for the duration of the ingest. The
IngestionService calls emit() as it works (per N thumbnails, per N embedded chunks, per
LV item); the writer buffers the lines and a background task flushes them every
settings.activity_flush_seconds. Each flush refreshes the job's lease
(ingest_jobs.locked_at), so the activity stream doubles as the worker's liveness signal:
a live job keeps its lease fresh, a dead one's goes stale and is reclaimed. Flush
failures are logged loudly (the lease depends on them) but never abort the ingest.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from shared.config import settings
from shared.models.ingestion_activity import NewIngestionActivity
from shared.services.ingestion.ingestion_service import UnitOfWorkFactory

logger = logging.getLogger(__name__)


class ActivityWriter:
    """Per-job buffered activity sink whose periodic flush also refreshes the job
    lease."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        worker_id: str,
        job_uuid: UUID,
        document_uuid: UUID,
        flush_seconds: float | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._worker_id = worker_id
        self._job_uuid = job_uuid
        self._document_uuid = document_uuid
        self._flush_seconds = (
            flush_seconds
            if flush_seconds is not None
            else settings.activity_flush_seconds
        )
        self._buffer: list[NewIngestionActivity] = []
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def emit(self, message: str, phase: str | None = None) -> None:
        """Buffer one activity line (non-blocking; the background task persists it)."""
        self._buffer.append(
            NewIngestionActivity(
                job_uuid=self._job_uuid,
                document_uuid=self._document_uuid,
                worker_id=self._worker_id,
                phase=phase,
                message=message,
            )
        )

    async def _flush(self) -> None:
        """Persist buffered lines and refresh the lease in one transaction. The lease is
        touched even when the buffer is empty, so a long stage with no emits is still
        kept alive."""
        pending, self._buffer = self._buffer, []
        async with self._uow_factory() as uow:
            if pending:
                await uow.ingestion_activity.add_many(pending)
            await uow.ingest_jobs.touch_lease(self._job_uuid, self._worker_id)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._flush_seconds)
            except asyncio.TimeoutError:
                pass
            try:
                await self._flush()
            except Exception:
                # Liveness-critical: a missed flush lets the lease go stale and risks a
                # false reclaim (idempotent, so it self-corrects). Log loudly, keep the
                # loop alive.
                logger.exception(
                    "activity flush failed for job %s (lease may go stale)",
                    self._job_uuid,
                )

    async def __aenter__(self) -> ActivityWriter:
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        try:
            await self._flush()
        except Exception:
            logger.exception("final activity flush failed for job %s", self._job_uuid)
