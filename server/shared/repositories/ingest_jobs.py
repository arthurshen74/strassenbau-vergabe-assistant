from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, func, insert, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.ingestion_activity_log import ingestion_activity_log
from shared.db.tables.projects import projects
from shared.models.console_job import ConsoleJobRow
from shared.models.enums import ConsoleJobKind, IngestStatus
from shared.models.ingest_job import (
    IngestJob,
    IngestJobStatusRow,
    NewIngestJob,
)
from shared.repositories.project_info_jobs import OPEN_STATUSES


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

    async def latest_for_document(self, document_uuid: UUID) -> IngestJob | None:
        """The most recent ingest job for a document, or None if it has never been
        ingested."""
        stmt = (
            select(ingest_jobs)
            .where(ingest_jobs.c.document_uuid == document_uuid)
            .order_by(ingest_jobs.c.created_at.desc())
            .limit(1)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def set_status(
        self,
        job_uuid: UUID,
        status: IngestStatus,
        *,
        expected_worker: str | None = None,
    ) -> IngestJob | None:
        """Set a job's status and clear its lease. When expected_worker is given the
        write is fenced (`AND locked_by = expected_worker`), so a worker whose job was
        reclaimed mid-run cannot clobber the new owner's status. Returns the row, or
        None if not found or the lease was lost."""
        stmt = update(ingest_jobs).where(ingest_jobs.c.job_uuid == job_uuid)
        if expected_worker is not None:
            stmt = stmt.where(ingest_jobs.c.locked_by == expected_worker)
        stmt = stmt.values(status=status, locked_at=None).returning(ingest_jobs)
        row = (await self.conn.execute(stmt)).mappings().first()
        return IngestJob.model_validate(dict(row)) if row else None

    async def status_for_project(self, project_uuid: UUID) -> list[IngestJobStatusRow]:
        """One row per job in the project: its status plus its latest progress event.

        DISTINCT ON keeps only the newest event per job; the outer left join attaches it
        to the job (queued jobs with no events yet have null latest_* fields)."""
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
                ).outerjoin(
                    latest_events, latest_events.c.job_uuid == ingest_jobs.c.job_uuid
                )
            )
            .where(documents.c.project_uuid == project_uuid)
            .order_by(ingest_jobs.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestJobStatusRow.model_validate(dict(r)) for r in rows]

    async def claim_next(
        self, *, worker_id: str, lease_seconds: float, max_attempts: int
    ) -> IngestJob | None:
        """Claim the oldest queued job, or reclaim an expired RUNNING one, and mark it
        RUNNING under this worker's lease. FOR UPDATE SKIP LOCKED lets concurrent
        workers each grab a distinct job without blocking. A RUNNING job is reclaimable
        once its lease has gone stale (no flush bumped locked_at within lease_seconds)
        and it still has retry budget; the claim increments attempts. Returns None when
        nothing is claimable."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        expired = and_(
            ingest_jobs.c.status == IngestStatus.RUNNING,
            func.coalesce(ingest_jobs.c.locked_at, ingest_jobs.c.created_at) < cutoff,
            ingest_jobs.c.attempts < max_attempts,
        )
        locked = (
            await self.conn.execute(
                select(ingest_jobs.c.job_uuid)
                .where(or_(ingest_jobs.c.status == IngestStatus.QUEUED, expired))
                .order_by(ingest_jobs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if locked is None:
            return None
        row = (
            (
                await self.conn.execute(
                    update(ingest_jobs)
                    .where(ingest_jobs.c.job_uuid == locked)
                    .values(
                        status=IngestStatus.RUNNING,
                        locked_at=func.now(),
                        locked_by=worker_id,
                        attempts=ingest_jobs.c.attempts + 1,
                    )
                    .returning(ingest_jobs)
                )
            )
            .mappings()
            .one()
        )
        return IngestJob.model_validate(dict(row))

    async def touch_lease(self, job_uuid: UUID, worker_id: str) -> None:
        """Refresh a job's lease (locked_at = now) while this worker still owns it.
        Called by the activity flush so a live job's lease stays fresh and is not
        reclaimed."""
        await self.conn.execute(
            update(ingest_jobs)
            .where(
                ingest_jobs.c.job_uuid == job_uuid,
                ingest_jobs.c.locked_by == worker_id,
            )
            .values(locked_at=func.now())
        )

    async def park_exhausted(self, *, lease_seconds: float, max_attempts: int) -> int:
        """Mark FAILED any RUNNING job whose lease has expired and whose retry budget is
        spent, so a poison job (one that keeps crashing its worker) stops being
        reclaimed and surfaces to the console. Returns the number parked."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        result = await self.conn.execute(
            update(ingest_jobs)
            .where(
                ingest_jobs.c.status == IngestStatus.RUNNING,
                func.coalesce(ingest_jobs.c.locked_at, ingest_jobs.c.created_at)
                < cutoff,
                ingest_jobs.c.attempts >= max_attempts,
            )
            .values(status=IngestStatus.FAILED, locked_at=None)
        )
        return result.rowcount

    async def requeue(self, job_uuid: UUID) -> IngestJob | None:
        """Reset a job in place to QUEUED, clearing its lease and retry count, so the
        worker reprocesses it (ingestion is idempotent). Returns the row, or None if not
        found."""
        row = (
            (
                await self.conn.execute(
                    update(ingest_jobs)
                    .where(ingest_jobs.c.job_uuid == job_uuid)
                    .values(
                        status=IngestStatus.QUEUED,
                        locked_at=None,
                        locked_by=None,
                        attempts=0,
                    )
                    .returning(ingest_jobs)
                )
            )
            .mappings()
            .first()
        )
        return IngestJob.model_validate(dict(row)) if row else None

    async def list_for_console(
        self,
        *,
        statuses: Sequence[IngestStatus] | None = None,
        project_uuid: UUID | None = None,
        recent_minutes: int | None = None,
    ) -> list[ConsoleJobRow]:
        """Jobs for the ops console, newest first, joined to each job's document file
        name, project name and latest activity line, optionally filtered to a set of
        statuses and/or a project. With `recent_minutes`, only open jobs and jobs
        updated within that window are returned."""
        latest = (
            select(
                ingestion_activity_log.c.phase.label("latest_phase"),
                ingestion_activity_log.c.message.label("latest_message"),
                ingestion_activity_log.c.ts.label("latest_ts"),
            )
            .where(ingestion_activity_log.c.job_uuid == ingest_jobs.c.job_uuid)
            .order_by(ingestion_activity_log.c.id.desc())
            .limit(1)
            .lateral("latest_activity")
        )
        stmt = select(
            ingest_jobs.c.job_uuid,
            documents.c.project_uuid,
            projects.c.project_name,
            ingest_jobs.c.document_uuid,
            documents.c.file_name,
            ingest_jobs.c.status,
            ingest_jobs.c.attempts,
            ingest_jobs.c.locked_by,
            ingest_jobs.c.locked_at,
            ingest_jobs.c.created_at,
            ingest_jobs.c.updated_at,
            latest.c.latest_phase,
            latest.c.latest_message,
            latest.c.latest_ts,
        ).select_from(
            ingest_jobs.join(
                documents, ingest_jobs.c.document_uuid == documents.c.document_uuid
            )
            .join(projects, documents.c.project_uuid == projects.c.project_uuid)
            .outerjoin(latest, true())
        )
        if statuses:
            stmt = stmt.where(ingest_jobs.c.status.in_(statuses))
        if project_uuid is not None:
            stmt = stmt.where(documents.c.project_uuid == project_uuid)
        if recent_minutes is not None:
            cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, recent_minutes)
            stmt = stmt.where(
                or_(
                    ingest_jobs.c.status.in_(OPEN_STATUSES),
                    ingest_jobs.c.updated_at >= cutoff,
                )
            )
        stmt = stmt.order_by(ingest_jobs.c.created_at.desc())
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [ConsoleJobRow(kind=ConsoleJobKind.INGEST, **dict(r)) for r in rows]
