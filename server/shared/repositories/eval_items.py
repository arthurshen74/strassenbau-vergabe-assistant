from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_items import eval_items
from shared.domain.eval_item import EvalItem, NewEvalItem


class EvalItemRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, eval_item_uuid: UUID) -> EvalItem | None:
        row = (
            await self.conn.execute(
                select(eval_items).where(eval_items.c.eval_item_uuid == eval_item_uuid)
            )
        ).mappings().first()
        return EvalItem.model_validate(dict(row)) if row else None

    async def list_by_question(self, question_uuid: UUID) -> Sequence[EvalItem]:
        stmt = (
            select(eval_items)
            .where(eval_items.c.question_uuid == question_uuid)
            .order_by(eval_items.c.created_at.asc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalItem.model_validate(dict(r)) for r in rows]

    async def list_by_project(self, project_uuid: UUID) -> Sequence[EvalItem]:
        stmt = (
            select(eval_items)
            .where(eval_items.c.project_uuid == project_uuid)
            .order_by(eval_items.c.created_at.asc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EvalItem.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewEvalItem) -> EvalItem:
        stmt = insert(eval_items).values(**new.model_dump()).returning(eval_items)
        row = (await self.conn.execute(stmt)).mappings().one()
        return EvalItem.model_validate(dict(row))

    async def update(self, eval_item_uuid: UUID, **changes: Any) -> EvalItem | None:
        if not changes:
            return await self.get(eval_item_uuid)
        stmt = (
            update(eval_items)
            .where(eval_items.c.eval_item_uuid == eval_item_uuid)
            .values(**changes)
            .returning(eval_items)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return EvalItem.model_validate(dict(row)) if row else None

    async def delete(self, eval_item_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(eval_items).where(eval_items.c.eval_item_uuid == eval_item_uuid)
        )
        return result.rowcount > 0
