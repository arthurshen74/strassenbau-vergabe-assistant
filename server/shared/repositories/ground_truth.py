from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.calculation_ground_truth import calculation_ground_truth
from shared.models.ground_truth import GroundTruth, NewGroundTruth


class GroundTruthRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def upsert(self, new: NewGroundTruth) -> GroundTruth:
        """Insert the position's gold record, or update it in place when one already
        exists (the latest review wins). Keyed by (project_uuid, lv_item_uuid)."""
        values = new.model_dump()
        stmt = pg_insert(calculation_ground_truth).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                calculation_ground_truth.c.project_uuid,
                calculation_ground_truth.c.lv_item_uuid,
            ],
            set_={
                "source_conversation_uuid": stmt.excluded.source_conversation_uuid,
                "oz": stmt.excluded.oz,
                "leistung_key": stmt.excluded.leistung_key,
                "bauverfahren_key": stmt.excluded.bauverfahren_key,
                "gold_variables": stmt.excluded.gold_variables,
                "created_by_user_id": stmt.excluded.created_by_user_id,
                "updated_at": func.now(),
            },
        ).returning(calculation_ground_truth)
        row = (await self.conn.execute(stmt)).mappings().one()
        return GroundTruth.model_validate(dict(row))

    async def get(self, project_uuid: UUID, lv_item_uuid: UUID) -> GroundTruth | None:
        stmt = select(calculation_ground_truth).where(
            calculation_ground_truth.c.project_uuid == project_uuid,
            calculation_ground_truth.c.lv_item_uuid == lv_item_uuid,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return GroundTruth.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> list[GroundTruth]:
        stmt = (
            select(calculation_ground_truth)
            .where(calculation_ground_truth.c.project_uuid == project_uuid)
            .order_by(calculation_ground_truth.c.updated_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [GroundTruth.model_validate(dict(r)) for r in rows]

    async def delete(self, project_uuid: UUID, lv_item_uuid: UUID) -> bool:
        """Remove the position's gold record; False when there was none."""
        stmt = delete(calculation_ground_truth).where(
            calculation_ground_truth.c.project_uuid == project_uuid,
            calculation_ground_truth.c.lv_item_uuid == lv_item_uuid,
        )
        result = await self.conn.execute(stmt)
        return result.rowcount > 0
