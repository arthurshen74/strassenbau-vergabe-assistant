"""Repository for ner_flags: CRUD plus the effective-category aggregation that backs the
dashboard summary (user override wins over the LLM assignment)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ner_flags import ner_flags
from shared.models.enums import NerFailureCategory, NerFlagKind, NerFlagStatus
from shared.models.ner_flag import (
    NerCategoryCount,
    NerFlag,
    NerFlagSummary,
    NewNerFlag,
)


def _effective_category() -> Any:
    return func.coalesce(ner_flags.c.category_override, ner_flags.c.category)


class NerFlagRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewNerFlag) -> NerFlag:
        values = new.model_dump(mode="json")
        stmt = insert(ner_flags).values(**values).returning(ner_flags)
        row = (await self.conn.execute(stmt)).mappings().one()
        return NerFlag.model_validate(dict(row))

    async def get(self, ner_flag_uuid: UUID) -> NerFlag | None:
        stmt = select(ner_flags).where(ner_flags.c.ner_flag_uuid == ner_flag_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return NerFlag.model_validate(dict(row)) if row else None

    async def list(
        self,
        kind: NerFlagKind | None = None,
        category: NerFailureCategory | None = None,
        status: NerFlagStatus | None = None,
    ) -> list[NerFlag]:
        stmt = select(ner_flags)
        if kind is not None:
            stmt = stmt.where(ner_flags.c.kind == kind.value)
        if category is not None:
            stmt = stmt.where(_effective_category() == category.value)
        if status is not None:
            stmt = stmt.where(ner_flags.c.status == status.value)
        stmt = stmt.order_by(ner_flags.c.created_at.desc())
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [NerFlag.model_validate(dict(r)) for r in rows]

    async def update(self, ner_flag_uuid: UUID, **changes: Any) -> NerFlag | None:
        if not changes:
            return await self.get(ner_flag_uuid)
        stmt = (
            update(ner_flags)
            .where(ner_flags.c.ner_flag_uuid == ner_flag_uuid)
            .values(**changes)
            .returning(ner_flags)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return NerFlag.model_validate(dict(row)) if row else None

    async def delete(self, ner_flag_uuid: UUID) -> None:
        stmt = delete(ner_flags).where(ner_flags.c.ner_flag_uuid == ner_flag_uuid)
        await self.conn.execute(stmt)

    async def category_counts(self) -> NerFlagSummary:
        """Flag tallies grouped by effective category and split by status."""
        effective = _effective_category()
        stmt = select(
            effective.label("category"),
            ner_flags.c.status,
            func.count().label("count"),
        ).group_by(effective, ner_flags.c.status)
        rows = (await self.conn.execute(stmt)).mappings().all()

        buckets: dict[str | None, dict[str, int]] = {}
        total = 0
        for row in rows:
            count = row["count"]
            total += count
            bucket = buckets.setdefault(row["category"], {"open": 0, "resolved": 0})
            if row["status"] == NerFlagStatus.RESOLVED.value:
                bucket["resolved"] += count
            else:
                bucket["open"] += count

        by_category = [
            NerCategoryCount(
                category=category,
                open_count=bucket["open"],
                resolved_count=bucket["resolved"],
                total=bucket["open"] + bucket["resolved"],
            )
            for category, bucket in buckets.items()
        ]
        by_category.sort(key=lambda c: c.total, reverse=True)
        return NerFlagSummary(total=total, by_category=by_category)
