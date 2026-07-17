from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.entity_rule import NewEntityRule
from shared.repositories.entity_rules import EntityRuleRepository


async def test_add_list_get_round_trip(conn: AsyncConnection) -> None:
    repo = EntityRuleRepository(conn)
    created = await repo.add(
        NewEntityRule(
            label="BAUSTOFF",
            pattern=[{"ORTH": "Asphaltbeton"}],
            pattern_id="baustoff_asphalt",
        )
    )
    assert created.enabled is True
    assert created.pattern == [{"ORTH": "Asphaltbeton"}]

    fetched = await repo.get(created.entity_rule_uuid)
    assert fetched is not None
    assert fetched.entity_rule_uuid == created.entity_rule_uuid

    listed = await repo.list()
    assert [r.entity_rule_uuid for r in listed] == [created.entity_rule_uuid]


async def test_list_enabled_excludes_disabled(conn: AsyncConnection) -> None:
    repo = EntityRuleRepository(conn)
    on = await repo.add(NewEntityRule(label="EINHEIT", pattern="cm"))
    off = await repo.add(NewEntityRule(label="EINHEIT", pattern="mm", enabled=False))

    enabled_ids = {r.entity_rule_uuid for r in await repo.list_enabled()}
    assert on.entity_rule_uuid in enabled_ids
    assert off.entity_rule_uuid not in enabled_ids


async def test_update_partial_and_delete(conn: AsyncConnection) -> None:
    repo = EntityRuleRepository(conn)
    rule = await repo.add(NewEntityRule(label="BAUSTOFF", pattern="Beton"))

    updated = await repo.update(rule.entity_rule_uuid, enabled=False)
    assert updated is not None
    assert updated.enabled is False
    assert updated.label == "BAUSTOFF"  # untouched field preserved

    await repo.delete(rule.entity_rule_uuid)
    assert await repo.get(rule.entity_rule_uuid) is None


async def test_labels_distinct(conn: AsyncConnection) -> None:
    repo = EntityRuleRepository(conn)
    await repo.add(NewEntityRule(label="BAUSTOFF", pattern="Beton"))
    await repo.add(NewEntityRule(label="BAUSTOFF", pattern="Asphalt"))
    await repo.add(NewEntityRule(label="EINHEIT", pattern="cm"))

    assert await repo.labels() == ["BAUSTOFF", "EINHEIT"]
