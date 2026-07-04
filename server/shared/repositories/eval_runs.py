from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_runs import eval_runs
from shared.models.enums import EvalRunStatus
from shared.models.eval_run import EvalRun, NewEvalRun


class EvalRunRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewEvalRun) -> EvalRun:
        stmt = insert(eval_runs).values(**new.model_dump()).returning(eval_runs)
        row = (await self.conn.execute(stmt)).mappings().one()
        return EvalRun.model_validate(dict(row))

    async def get(self, eval_run_uuid: UUID) -> EvalRun | None:
        stmt = select(eval_runs).where(eval_runs.c.eval_run_uuid == eval_run_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return EvalRun.model_validate(dict(row)) if row else None

    async def list(
        self, *, project_uuid: UUID | None = None, limit: int = 50
    ) -> list[EvalRun]:
        stmt = select(eval_runs).order_by(eval_runs.c.created_at.desc()).limit(limit)
        if project_uuid is not None:
            stmt = stmt.where(eval_runs.c.project_uuid == project_uuid)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalRun.model_validate(dict(r)) for r in rows]

    async def claim_next(
        self, *, worker_id: str, lease_seconds: float, max_attempts: int
    ) -> EvalRun | None:
        """Claim the oldest queued run, or reclaim an expired RUNNING one, and mark it RUNNING
        under this worker's lease. Same mechanics as IngestJobRepository.claim_next: FOR UPDATE
        SKIP LOCKED hands concurrent workers distinct runs; the claim increments attempts."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        expired = and_(
            eval_runs.c.status == EvalRunStatus.RUNNING,
            func.coalesce(eval_runs.c.locked_at, eval_runs.c.created_at) < cutoff,
            eval_runs.c.attempts < max_attempts,
        )
        locked = (
            await self.conn.execute(
                select(eval_runs.c.eval_run_uuid)
                .where(or_(eval_runs.c.status == EvalRunStatus.QUEUED, expired))
                .order_by(eval_runs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if locked is None:
            return None
        row = (
            await self.conn.execute(
                update(eval_runs)
                .where(eval_runs.c.eval_run_uuid == locked)
                .values(
                    status=EvalRunStatus.RUNNING,
                    locked_at=func.now(),
                    locked_by=worker_id,
                    attempts=eval_runs.c.attempts + 1,
                )
                .returning(eval_runs)
            )
        ).mappings().one()
        return EvalRun.model_validate(dict(row))

    async def touch_lease(self, eval_run_uuid: UUID, worker_id: str) -> None:
        """Refresh the lease (locked_at = now) while this worker still owns the run; every
        progress event does this so a long run is not reclaimed mid-flight."""
        await self.conn.execute(
            update(eval_runs)
            .where(
                eval_runs.c.eval_run_uuid == eval_run_uuid,
                eval_runs.c.locked_by == worker_id,
            )
            .values(locked_at=func.now())
        )

    async def finalize(
        self,
        eval_run_uuid: UUID,
        *,
        status: EvalRunStatus,
        expected_worker: str,
        summary: dict[str, Any] | None = None,
        prompt_versions: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> EvalRun | None:
        """Terminal status write, fenced on the lease (locked_by = expected_worker) so a worker
        whose run was reclaimed mid-flight cannot clobber the new owner. Returns None when the
        lease was lost."""
        row = (
            await self.conn.execute(
                update(eval_runs)
                .where(
                    eval_runs.c.eval_run_uuid == eval_run_uuid,
                    eval_runs.c.locked_by == expected_worker,
                )
                .values(
                    status=status,
                    locked_at=None,
                    summary=summary,
                    prompt_versions=prompt_versions,
                    error=error,
                )
                .returning(eval_runs)
            )
        ).mappings().first()
        return EvalRun.model_validate(dict(row)) if row else None

    async def park_exhausted(self, *, lease_seconds: float, max_attempts: int) -> int:
        """Mark FAILED any RUNNING run whose lease has expired and whose retry budget is spent,
        so a poison run stops being reclaimed. Returns the number parked."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)
        result = await self.conn.execute(
            update(eval_runs)
            .where(
                eval_runs.c.status == EvalRunStatus.RUNNING,
                func.coalesce(eval_runs.c.locked_at, eval_runs.c.created_at) < cutoff,
                eval_runs.c.attempts >= max_attempts,
            )
            .values(status=EvalRunStatus.FAILED, locked_at=None, error="lease expired, retries exhausted")
        )
        return result.rowcount
