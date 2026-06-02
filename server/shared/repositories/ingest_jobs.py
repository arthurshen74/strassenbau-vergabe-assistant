from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.models.enums import IngestStatus
from shared.models.ingest_job import IngestJob, IngestJobStatusRow, NewIngestJob


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

    async def status_for_project(self, project_uuid: UUID) -> list[IngestJobStatusRow]:
        """One row per job in the project: its status plus its latest progress event.

        DISTINCT ON keeps only the newest event per job; the outer left join attaches it to the
        job (queued jobs with no events yet have null latest_* fields)."""
        latest_events = (
            select(
                ingest_job_events.c.job_uuid,
                ingest_job_events.c.event.label("latest_event"),
                ingest_job_events.c.pipeline_phase.label("latest_phase"),
                ingest_job_events.c.message.label("latest_message"),
                ingest_job_events.c.ts.label("latest_ts"),
            )
            .distinct(ingest_job_events.c.job_uuid)
            .order_by(ingest_job_events.c.job_uuid, ingest_job_events.c.ts.desc())
            .subquery()
        )
        stmt = (
            select(
                ingest_jobs.c.document_uuid,
                ingest_jobs.c.job_uuid,
                ingest_jobs.c.status,
                latest_events.c.latest_event,
                latest_events.c.latest_phase,
                latest_events.c.latest_message,
                latest_events.c.latest_ts,
            )
            .select_from(
                ingest_jobs.join(
                    documents, ingest_jobs.c.document_uuid == documents.c.document_uuid
                ).outerjoin(latest_events, latest_events.c.job_uuid == ingest_jobs.c.job_uuid)
            )
            .where(documents.c.project_uuid == project_uuid)
            .order_by(ingest_jobs.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestJobStatusRow.model_validate(dict(r)) for r in rows]

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
