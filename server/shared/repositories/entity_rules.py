from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, distinct, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.entity_rules import entity_rules
from shared.models.entity_rule import EntityRule, NewEntityRule


class EntityRuleRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def list(self) -> list[EntityRule]:
        """Every rule regardless of enabled state, ordered by label then created_at."""
        stmt = select(entity_rules).order_by(
            entity_rules.c.label, entity_rules.c.created_at
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EntityRule.model_validate(dict(r)) for r in rows]

    async def list_enabled(self) -> list[EntityRule]:
        """Only enabled rules — the set compiled into the live pipeline."""
        stmt = (
            select(entity_rules)
            .where(entity_rules.c.enabled)
            .order_by(entity_rules.c.label, entity_rules.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [EntityRule.model_validate(dict(r)) for r in rows]

    async def labels(self) -> list[str]:
        """Distinct labels currently in use, for the admin UI's autocomplete."""
        stmt = select(distinct(entity_rules.c.label)).order_by(entity_rules.c.label)
        return list((await self.conn.execute(stmt)).scalars().all())

    async def get(self, entity_rule_uuid: UUID) -> EntityRule | None:
        stmt = select(entity_rules).where(
            entity_rules.c.entity_rule_uuid == entity_rule_uuid
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return EntityRule.model_validate(dict(row)) if row else None

    async def add(self, new: NewEntityRule) -> EntityRule:
        stmt = insert(entity_rules).values(**new.model_dump()).returning(entity_rules)
        row = (await self.conn.execute(stmt)).mappings().one()
        return EntityRule.model_validate(dict(row))

    async def update(self, entity_rule_uuid: UUID, **changes: Any) -> EntityRule | None:
        if not changes:
            return await self.get(entity_rule_uuid)
        stmt = (
            update(entity_rules)
            .where(entity_rules.c.entity_rule_uuid == entity_rule_uuid)
            .values(**changes)
            .returning(entity_rules)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return EntityRule.model_validate(dict(row)) if row else None

    async def delete(self, entity_rule_uuid: UUID) -> None:
        stmt = delete(entity_rules).where(
            entity_rules.c.entity_rule_uuid == entity_rule_uuid
        )
        await self.conn.execute(stmt)
