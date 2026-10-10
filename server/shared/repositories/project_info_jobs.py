from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, exists, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.project_info_jobs import project_info_jobs
from shared.models.enums import IngestStatus, ProjectInfoQuery
from shared.models.project_info_job import (
    NewProjectInfoJob,
    ProjectInfoJob,
    ProjectInfoResult,
)

OPEN_STATUSES = (IngestStatus.QUEUED, IngestStatus.RUNNING)


class ProjectInfoJobRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewProjectInfoJob) -> ProjectInfoJob:
        stmt = (
            insert(project_info_jobs)
            .values(**new.model_dump())
            .returning(project_info_jobs)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return ProjectInfoJob.model_validate(dict(row))

    async def get(self, job_uuid: UUID) -> ProjectInfoJob | None:
        stmt = select(project_info_jobs).where(project_info_jobs.c.job_uuid == job_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return ProjectInfoJob.model_validate(dict(row)) if row else None

    async def claim_next(
        self, *, worker_id: str, lease_seconds: float, max_attempts: int
    ) -> ProjectInfoJob | None:
        """Claim the oldest queued job, or reclaim an expired RUNNING one, whose project
        has no queued or running ingest job, and mark it RUNNING under this worker's
        lease (FOR UPDATE SKIP LOCKED, as IngestJobRepository.claim_next). FAILED ingest
        jobs do not block: one poison document would otherwise hold the project's info
        job forever. Returns None when nothing is claimable."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        expired = and_(
            project_info_jobs.c.status == IngestStatus.RUNNING,
            func.coalesce(project_info_jobs.c.locked_at, project_info_jobs.c.created_at)
            < cutoff,
            project_info_jobs.c.attempts < max_attempts,
        )
        ingest_pending = exists().where(
            ingest_jobs.c.document_uuid == documents.c.document_uuid,
            documents.c.project_uuid == project_info_jobs.c.project_uuid,
            ingest_jobs.c.status.in_(OPEN_STATUSES),
        )
        locked = (
            await self.conn.execute(
                select(project_info_jobs.c.job_uuid)
                .where(
                    or_(project_info_jobs.c.status == IngestStatus.QUEUED, expired),
                    ~ingest_pending,
                )
                .order_by(project_info_jobs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True, of=project_info_jobs)
            )
        ).scalar_one_or_none()
        if locked is None:
            return None
        row = (
            (
                await self.conn.execute(
                    update(project_info_jobs)
                    .where(project_info_jobs.c.job_uuid == locked)
                    .values(
                        status=IngestStatus.RUNNING,
                        locked_at=func.now(),
                        locked_by=worker_id,
                        attempts=project_info_jobs.c.attempts + 1,
                    )
                    .returning(project_info_jobs)
                )
            )
            .mappings()
            .one()
        )
        return ProjectInfoJob.model_validate(dict(row))

    async def set_status(
        self,
        job_uuid: UUID,
        status: IngestStatus,
        *,
        expected_worker: str,
        error: str | None = None,
        result: dict[ProjectInfoQuery, ProjectInfoResult] | None = None,
    ) -> ProjectInfoJob | None:
        """Terminal status write that clears the lease, fenced on `locked_by =
        expected_worker` so a worker whose job was reclaimed mid-run cannot clobber the
        new owner. Returns None when the lease was lost."""
        stored = (
            {key.value: r.model_dump(mode="json") for key, r in result.items()}
            if result is not None
            else None
        )
        stmt = (
            update(project_info_jobs)
            .where(
                project_info_jobs.c.job_uuid == job_uuid,
                project_info_jobs.c.locked_by == expected_worker,
            )
            .values(status=status, locked_at=None, error=error, result=stored)
            .returning(project_info_jobs)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return ProjectInfoJob.model_validate(dict(row)) if row else None

    async def touch_lease(self, job_uuid: UUID, worker_id: str) -> None:
        """Refresh a job's lease (locked_at = now) while this worker still owns it."""
        await self.conn.execute(
            update(project_info_jobs)
            .where(
                project_info_jobs.c.job_uuid == job_uuid,
                project_info_jobs.c.locked_by == worker_id,
            )
            .values(locked_at=func.now())
        )

    async def park_exhausted(self, *, lease_seconds: float, max_attempts: int) -> int:
        """Mark FAILED any RUNNING job whose lease has expired and whose retry budget is
        spent. Returns the number parked."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        result = await self.conn.execute(
            update(project_info_jobs)
            .where(
                project_info_jobs.c.status == IngestStatus.RUNNING,
                func.coalesce(
                    project_info_jobs.c.locked_at, project_info_jobs.c.created_at
                )
                < cutoff,
                project_info_jobs.c.attempts >= max_attempts,
            )
            .values(status=IngestStatus.FAILED, locked_at=None)
        )
        return result.rowcount

    async def latest_for_project(self, project_uuid: UUID) -> ProjectInfoJob | None:
        stmt = (
            select(project_info_jobs)
            .where(project_info_jobs.c.project_uuid == project_uuid)
            .order_by(project_info_jobs.c.created_at.desc())
            .limit(1)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return ProjectInfoJob.model_validate(dict(row)) if row else None

    async def open_job(self, project_uuid: UUID) -> ProjectInfoJob | None:
        """The project's queued or running job, if any; a re-run request returns it
        instead of enqueuing a second."""
        stmt = (
            select(project_info_jobs)
            .where(
                project_info_jobs.c.project_uuid == project_uuid,
                project_info_jobs.c.status.in_(OPEN_STATUSES),
            )
            .order_by(project_info_jobs.c.created_at.desc())
            .limit(1)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return ProjectInfoJob.model_validate(dict(row)) if row else None
