from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_jobs import ingest_jobs
from shared.domain.ingest_job import IngestJob, IngestStatus, NewIngestJob


class IngestJobRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, ingest_job_uuid: UUID) -> IngestJob | None:
        row = (
            await self.conn.execute(
                select(ingest_jobs).where(
                    ingest_jobs.c.ingest_job_uuid == ingest_job_uuid
                )
            )
        ).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> Sequence[IngestJob]:
        stmt = (
            select(ingest_jobs)
            .where(ingest_jobs.c.project_uuid == project_uuid)
            .order_by(ingest_jobs.c.created_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestJob.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewIngestJob) -> IngestJob:
        stmt = insert(ingest_jobs).values(**new.model_dump()).returning(ingest_jobs)
        row = (await self.conn.execute(stmt)).mappings().one()
        return IngestJob.model_validate(dict(row))

    async def set_status(
        self, ingest_job_uuid: UUID, status: IngestStatus
    ) -> IngestJob | None:
        stmt = (
            update(ingest_jobs)
            .where(ingest_jobs.c.ingest_job_uuid == ingest_job_uuid)
            .values(status=status)
            .returning(ingest_jobs)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def claim_next(self) -> IngestJob | None:
        """Dequeue the oldest queued job (FOR UPDATE SKIP LOCKED) and mark it running."""
        claimed = (
            await self.conn.execute(
                select(ingest_jobs.c.ingest_job_uuid)
                .where(ingest_jobs.c.status == IngestStatus.QUEUED)
                .order_by(ingest_jobs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if claimed is None:
            return None
        row = (
            await self.conn.execute(
                update(ingest_jobs)
                .where(ingest_jobs.c.ingest_job_uuid == claimed)
                .values(status=IngestStatus.RUNNING)
                .returning(ingest_jobs)
            )
        ).mappings().one()
        return IngestJob.model_validate(dict(row))
