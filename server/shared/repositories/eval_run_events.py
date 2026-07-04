from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_run_events import eval_run_events
from shared.models.eval_run import EvalRunEvent


class EvalRunEventRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, eval_run_uuid: UUID, message: str) -> None:
        await self.conn.execute(
            insert(eval_run_events).values(eval_run_uuid=eval_run_uuid, message=message)
        )

    async def list_by_run(self, eval_run_uuid: UUID) -> list[EvalRunEvent]:
        stmt = (
            select(eval_run_events)
            .where(eval_run_events.c.eval_run_uuid == eval_run_uuid)
            .order_by(eval_run_events.c.ts)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalRunEvent.model_validate(dict(r)) for r in rows]
