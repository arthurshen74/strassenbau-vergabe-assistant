from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_jobs import ingest_jobs
from shared.models.enums import IngestStatus
from shared.models.ingest_job import IngestJob, NewIngestJob


class IngestJobRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewIngestJob) -> IngestJob:
        stmt = insert(ingest_jobs).values(**new.model_dump()).returning(ingest_jobs)
        row = (await self.conn.execute(stmt)).mappings().one()
        return IngestJob.model_validate(dict(row))

    async def get(self, job_uuid: UUID) -> IngestJob | None:
        stmt = select(ingest_jobs).where(ingest_jobs.c.job_uuid == job_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def set_status(self, job_uuid: UUID, status: IngestStatus) -> IngestJob | None:
        stmt = (
            update(ingest_jobs)
            .where(ingest_jobs.c.job_uuid == job_uuid)
            .values(status=status)
            .returning(ingest_jobs)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def claim_next(self) -> IngestJob | None:
        """Pop the oldest queued job and mark it RUNNING. FOR UPDATE SKIP LOCKED lets
        concurrent workers each grab a distinct job without blocking on one another."""
        locked = (
            await self.conn.execute(
                select(ingest_jobs.c.job_uuid)
                .where(ingest_jobs.c.status == IngestStatus.QUEUED)
                .order_by(ingest_jobs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if locked is None:
            return None
        row = (
            await self.conn.execute(
                update(ingest_jobs)
                .where(ingest_jobs.c.job_uuid == locked)
                .values(status=IngestStatus.RUNNING)
                .returning(ingest_jobs)
            )
        ).mappings().one()
        return IngestJob.model_validate(dict(row))
