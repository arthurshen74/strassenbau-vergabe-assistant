"""EntityRuleService: CRUD for entity rules with spaCy-validated writes.

Owns the two cross-cutting concerns the routes must not: validating a candidate
pattern against spaCy before it is persisted (raising ValueError on a bad pattern,
which the route maps to 422), and flipping the in-process ruler dirty flag *after*
a successful commit so the next analyze/render recompiles. Each mutation runs in its
own Unit of Work, so `mark_dirty` is reached only once the transaction has committed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import EntityRule, NewEntityRule
from shared.models.entity_rule_schema import EntityRuleCreate, EntityRuleUpdate
from shared.services.nlp.entity_ruler import mark_dirty, validate_pattern


class EntityRuleService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list(self) -> list[EntityRule]:
        async with unit_of_work(self._engine) as uow:
            return await uow.entity_rules.list()

    async def labels(self) -> list[str]:
        async with unit_of_work(self._engine) as uow:
            return await uow.entity_rules.labels()

    async def get(self, entity_rule_uuid: UUID) -> EntityRule | None:
        async with unit_of_work(self._engine) as uow:
            return await uow.entity_rules.get(entity_rule_uuid)

    async def create(self, payload: EntityRuleCreate) -> EntityRule:
        validate_pattern(payload.label, payload.pattern)
        async with unit_of_work(self._engine) as uow:
            created = await uow.entity_rules.add(NewEntityRule(**payload.model_dump()))
        mark_dirty()
        return created

    async def update(
        self, entity_rule_uuid: UUID, patch: EntityRuleUpdate
    ) -> EntityRule | None:
        changes = patch.model_dump(exclude_unset=True)
        async with unit_of_work(self._engine) as uow:
            current = await uow.entity_rules.get(entity_rule_uuid)
            if current is None:
                return None
            if "label" in changes or "pattern" in changes:
                validate_pattern(
                    changes.get("label", current.label),
                    changes.get("pattern", current.pattern),
                )
            updated = await uow.entity_rules.update(entity_rule_uuid, **changes)
        mark_dirty()
        return updated

    async def delete(self, entity_rule_uuid: UUID) -> None:
        async with unit_of_work(self._engine) as uow:
            await uow.entity_rules.delete(entity_rule_uuid)
        mark_dirty()
