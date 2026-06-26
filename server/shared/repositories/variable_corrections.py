from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.variable_corrections import variable_corrections
from shared.models.ground_truth import NewVariableCorrection, VariableCorrection


class VariableCorrectionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, news: list[NewVariableCorrection]) -> None:
        """Append override rows (one per changed variable). No-op for an empty list."""
        if not news:
            return
        await self.conn.execute(insert(variable_corrections), [n.model_dump() for n in news])

    async def list_by_project(self, project_uuid: UUID) -> list[VariableCorrection]:
        stmt = (
            select(variable_corrections)
            .where(variable_corrections.c.project_uuid == project_uuid)
            .order_by(variable_corrections.c.created_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [VariableCorrection.model_validate(dict(r)) for r in rows]
