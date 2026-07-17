"""Seed the entity_rules table from the authored JSON fixture.

Imports `server/shared/services/nlp/entity_rules.json` (the 240 hand-authored
EntityRuler patterns) into the DB. Idempotent: each rule's dedupe key is a hash of
its label, pattern_id, and canonicalized pattern JSON; rules whose key is already
present are skipped, so re-running never creates duplicates.

    uv run python -m scripts.seed_entity_rules
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

import shared.db.tables  # noqa: F401  -- registers all tables on the shared metadata
from shared.config import settings
from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import EntityRule, NewEntityRule

RULES_JSON = (
    Path(__file__).resolve().parents[1]
    / "shared"
    / "services"
    / "nlp"
    / "entity_rules.json"
)

# The fixture uses spaCy's `id` field; the domain column is `pattern_id`.
_FIXTURE_ID = "id"


def _dedupe_key(label: str, pattern_id: str | None, pattern: Any) -> str:
    """Stable identity for a rule: label + pattern_id + canonical pattern JSON."""
    canonical = json.dumps(pattern, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{label}|{pattern_id or ''}|{canonical}".encode()).hexdigest()


def _existing_key(rule: EntityRule) -> str:
    return _dedupe_key(rule.label, rule.pattern_id, rule.pattern)


async def main() -> None:
    fixture: list[dict[str, Any]] = json.loads(RULES_JSON.read_text(encoding="utf-8"))

    engine = create_async_engine(settings.database_url)
    try:
        async with unit_of_work(engine) as uow:
            existing = {_existing_key(r) for r in await uow.entity_rules.list()}
            inserted = 0
            for entry in fixture:
                pattern_id = entry.get(_FIXTURE_ID)
                key = _dedupe_key(entry["label"], pattern_id, entry["pattern"])
                if key in existing:
                    continue
                await uow.entity_rules.add(
                    NewEntityRule(
                        label=entry["label"],
                        pattern=entry["pattern"],
                        pattern_id=pattern_id,
                    )
                )
                existing.add(key)
                inserted += 1
        print(f"  entity_rules: {inserted} inserted, {len(fixture)} in fixture")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
