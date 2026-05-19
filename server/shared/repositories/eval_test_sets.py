from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_test_sets import eval_test_sets
from shared.domain.eval_test_set import EvalTestSet, NewEvalTestSet


class EvalTestSetRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, test_set_uuid: UUID) -> EvalTestSet | None:
        row = (
            await self.conn.execute(
                select(eval_test_sets).where(
                    eval_test_sets.c.test_set_uuid == test_set_uuid
                )
            )
        ).mappings().first()
        return EvalTestSet.model_validate(dict(row)) if row else None

    async def get_by_name(self, name: str) -> EvalTestSet | None:
        row = (
            await self.conn.execute(
                select(eval_test_sets).where(eval_test_sets.c.name == name)
            )
        ).mappings().first()
        return EvalTestSet.model_validate(dict(row)) if row else None

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[EvalTestSet]:
        stmt = (
            select(eval_test_sets)
            .order_by(eval_test_sets.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalTestSet.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewEvalTestSet) -> EvalTestSet:
        stmt = insert(eval_test_sets).values(**new.model_dump()).returning(eval_test_sets)
        row = (await self.conn.execute(stmt)).mappings().one()
        return EvalTestSet.model_validate(dict(row))

    async def update(self, test_set_uuid: UUID, **changes: Any) -> EvalTestSet | None:
        if not changes:
            return await self.get(test_set_uuid)
        stmt = (
            update(eval_test_sets)
            .where(eval_test_sets.c.test_set_uuid == test_set_uuid)
            .values(**changes)
            .returning(eval_test_sets)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return EvalTestSet.model_validate(dict(row)) if row else None

    async def delete(self, test_set_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(eval_test_sets).where(
                eval_test_sets.c.test_set_uuid == test_set_uuid
            )
        )
        return result.rowcount > 0
