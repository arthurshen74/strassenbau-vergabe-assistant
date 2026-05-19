from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import func

from shared.db.tables.eval_results import eval_results
from shared.domain.eval_result import EvalResult, NewEvalResult


class EvalResultRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, eval_result_uuid: UUID) -> EvalResult | None:
        row = (
            await self.conn.execute(
                select(eval_results).where(
                    eval_results.c.eval_result_uuid == eval_result_uuid
                )
            )
        ).mappings().first()
        return EvalResult.model_validate(dict(row)) if row else None

    async def list_by_test_set(self, test_set_uuid: UUID) -> Sequence[EvalResult]:
        stmt = (
            select(eval_results)
            .where(eval_results.c.test_set_uuid == test_set_uuid)
            .order_by(eval_results.c.ran_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalResult.model_validate(dict(r)) for r in rows]

    async def upsert(self, new: NewEvalResult) -> EvalResult:
        """Insert a new result, or overwrite an existing one for the same
        (eval_item_uuid, test_set_uuid) pair. Bumps ran_at on rerun."""
        values = new.model_dump()
        stmt = pg_insert(eval_results).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_eval_results_eval_item_test_set",
            set_={
                "ran_at": func.now(),
                "actual_result": stmt.excluded.actual_result,
                "passed": stmt.excluded.passed,
                "metrics": stmt.excluded.metrics,
            },
        ).returning(eval_results)
        row = (await self.conn.execute(stmt)).mappings().one()
        return EvalResult.model_validate(dict(row))

    async def delete(self, eval_result_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(eval_results).where(
                eval_results.c.eval_result_uuid == eval_result_uuid
            )
        )
        return result.rowcount > 0
