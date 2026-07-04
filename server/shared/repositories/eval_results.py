from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_results import eval_results
from shared.models.eval_run import EvalResult


class EvalResultRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(
        self, eval_run_uuid: UUID, rows: list[tuple[str, dict[str, Any]]]
    ) -> None:
        """Persist (item_id, payload) result rows for a finished run. No-op for an empty list."""
        if not rows:
            return
        await self.conn.execute(
            insert(eval_results),
            [
                {"eval_run_uuid": eval_run_uuid, "item_id": item_id, "payload": payload}
                for item_id, payload in rows
            ],
        )

    async def list_by_run(self, eval_run_uuid: UUID) -> list[EvalResult]:
        stmt = (
            select(eval_results)
            .where(eval_results.c.eval_run_uuid == eval_run_uuid)
            .order_by(eval_results.c.created_at, eval_results.c.item_id)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalResult.model_validate(dict(r)) for r in rows]
