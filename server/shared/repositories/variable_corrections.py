from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.variable_corrections import variable_corrections
from shared.models.enums import VariableCorrectionReason
from shared.models.ground_truth import (
    CorrectionSummaryRow,
    NewVariableCorrection,
    VariableCorrection,
)


class VariableCorrectionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, news: list[NewVariableCorrection]) -> None:
        """Append override rows (one per changed variable). No-op for an empty list."""
        if not news:
            return
        await self.conn.execute(
            insert(variable_corrections), [n.model_dump() for n in news]
        )

    async def list_by_project(
        self,
        project_uuid: UUID,
        *,
        variable_name: str | None = None,
        reason: VariableCorrectionReason | None = None,
    ) -> list[VariableCorrection]:
        stmt = (
            select(variable_corrections)
            .where(variable_corrections.c.project_uuid == project_uuid)
            .order_by(variable_corrections.c.created_at.desc())
        )
        if variable_name is not None:
            stmt = stmt.where(variable_corrections.c.variable_name == variable_name)
        if reason is not None:
            stmt = stmt.where(variable_corrections.c.reason == reason)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [VariableCorrection.model_validate(dict(r)) for r in rows]

    async def summary_by_project(
        self, project_uuid: UUID
    ) -> list[CorrectionSummaryRow]:
        """Correction counts grouped by variable and reason, most-corrected first."""
        stmt = (
            select(
                variable_corrections.c.variable_name,
                variable_corrections.c.reason,
                func.count().label("count"),
            )
            .where(variable_corrections.c.project_uuid == project_uuid)
            .group_by(
                variable_corrections.c.variable_name,
                variable_corrections.c.reason,
            )
            .order_by(func.count().desc(), variable_corrections.c.variable_name)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [CorrectionSummaryRow.model_validate(dict(r)) for r in rows]
