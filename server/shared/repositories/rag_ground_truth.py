from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.rag_ground_truth import rag_ground_truth
from shared.models.rag_ground_truth import (
    NewRagGroundTruth,
    RagGroundTruth,
    RagGroundTruthUpsert,
)


def _values(model: NewRagGroundTruth | RagGroundTruthUpsert) -> dict:
    # refs hold UUIDs, which the JSONB serializer can't take raw — dump them JSON-ready.
    values = model.model_dump()
    values["refs"] = [r.model_dump(mode="json") for r in model.refs]
    return values


class RagGroundTruthRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewRagGroundTruth) -> RagGroundTruth:
        stmt = (
            insert(rag_ground_truth).values(**_values(new)).returning(rag_ground_truth)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return RagGroundTruth.model_validate(dict(row))

    async def get(
        self, project_uuid: UUID, rag_ground_truth_uuid: UUID
    ) -> RagGroundTruth | None:
        stmt = select(rag_ground_truth).where(
            rag_ground_truth.c.project_uuid == project_uuid,
            rag_ground_truth.c.rag_ground_truth_uuid == rag_ground_truth_uuid,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return RagGroundTruth.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> list[RagGroundTruth]:
        stmt = (
            select(rag_ground_truth)
            .where(rag_ground_truth.c.project_uuid == project_uuid)
            .order_by(rag_ground_truth.c.updated_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [RagGroundTruth.model_validate(dict(r)) for r in rows]

    async def update(
        self,
        project_uuid: UUID,
        rag_ground_truth_uuid: UUID,
        payload: RagGroundTruthUpsert,
    ) -> RagGroundTruth | None:
        """Replace the curated content; None when the row is not in this project."""
        stmt = (
            update(rag_ground_truth)
            .where(
                rag_ground_truth.c.project_uuid == project_uuid,
                rag_ground_truth.c.rag_ground_truth_uuid == rag_ground_truth_uuid,
            )
            .values(**_values(payload), updated_at=func.now())
            .returning(rag_ground_truth)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return RagGroundTruth.model_validate(dict(row)) if row else None

    async def delete(self, project_uuid: UUID, rag_ground_truth_uuid: UUID) -> bool:
        stmt = delete(rag_ground_truth).where(
            rag_ground_truth.c.project_uuid == project_uuid,
            rag_ground_truth.c.rag_ground_truth_uuid == rag_ground_truth_uuid,
        )
        result = await self.conn.execute(stmt)
        return result.rowcount > 0
