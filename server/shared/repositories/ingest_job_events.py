from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.models.ingest_job_event import IngestJobEvent, NewIngestJobEvent


class IngestJobEventRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewIngestJobEvent) -> IngestJobEvent:
        stmt = (
            insert(ingest_job_events)
            .values(**new.model_dump())
            .returning(ingest_job_events)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return IngestJobEvent.model_validate(dict(row))

    async def list_for_job(self, job_uuid: UUID) -> list[IngestJobEvent]:
        stmt = (
            select(ingest_job_events)
            .where(ingest_job_events.c.job_uuid == job_uuid)
            .order_by(ingest_job_events.c.ts)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestJobEvent.model_validate(dict(r)) for r in rows]

    async def latest_event_ts(self, document_uuid: UUID, event: str) -> datetime | None:
        """Timestamp of the most recent matching event among a document's jobs, or None.
        Used for a document's 'last ingested' date (caller passes
        IngestEvent.COMPLETED.value)."""
        stmt = (
            select(func.max(ingest_job_events.c.ts))
            .select_from(
                ingest_job_events.join(
                    ingest_jobs, ingest_job_events.c.job_uuid == ingest_jobs.c.job_uuid
                )
            )
            .where(
                ingest_jobs.c.document_uuid == document_uuid,
                ingest_job_events.c.event == event,
            )
        )
        return (await self.conn.execute(stmt)).scalar_one()
