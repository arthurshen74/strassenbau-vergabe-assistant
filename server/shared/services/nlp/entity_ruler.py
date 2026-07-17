"""DB-backed EntityRuler: pattern compilation, spaCy validation, and lazy
invalidation of the ruler pipe on the shared spaCy singleton.

`compile_pattern_dicts` turns stored rules into the list of pattern dicts spaCy's
`EntityRuler.add_patterns` expects. `validate_pattern` compiles a single candidate
against a throwaway blank pipeline (design D7) so a bad pattern is rejected at the
write boundary, never against the live model.

Invalidation is an in-process dirty flag (design D3): any successful mutation calls
`mark_dirty()`; `ensure_ruler_current` checks it (cheaply) at the top of analyze/
render and rebuilds the `entity_ruler` pipe from the current enabled rules only when
dirty. The API runs single-process, so no DB-backed version row is needed.
"""

from __future__ import annotations

import threading
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import EntityPattern, EntityRule

ENTITY_RULER_PIPE = "entity_ruler"

# Config for the ruler pipe: domain rules override overlapping stock NER (design D5).
_ENTITY_RULER_CONFIG = {"overwrite_ents": True}


def compile_pattern_dicts(rules: list[EntityRule]) -> list[dict[str, Any]]:
    """Turn stored rules into spaCy EntityRuler pattern dicts.

    Each dict carries `label` and `pattern`; `id` is included only when the rule
    has a `pattern_id`, so it is echoed onto matched spans as `ent.ent_id_` for
    provenance.
    """
    dicts: list[dict[str, Any]] = []
    for rule in rules:
        entry: dict[str, Any] = {"label": rule.label, "pattern": rule.pattern}
        if rule.pattern_id is not None:
            entry["id"] = rule.pattern_id
        dicts.append(entry)
    return dicts


def validate_pattern(label: str, pattern: EntityPattern) -> None:
    """Compile one candidate pattern against a scratch blank spaCy pipeline.

    Raises ValueError with spaCy's underlying message if the pattern does not
    compile. Never touches the live singleton.
    """
    import spacy

    nlp = spacy.blank("de")
    ruler = nlp.add_pipe(ENTITY_RULER_PIPE, config=_ENTITY_RULER_CONFIG)
    try:
        ruler.add_patterns([{"label": label, "pattern": pattern}])
    except Exception as exc:  # spaCy raises MatchPatternError/ValueError subclasses
        raise ValueError(str(exc)) from exc


_dirty = True
_dirty_lock = threading.Lock()


def mark_dirty() -> None:
    """Flag the compiled ruler as stale; the next analyze/render recompiles it."""
    global _dirty
    with _dirty_lock:
        _dirty = True


async def ensure_ruler_current(nlp: Any, engine: AsyncEngine) -> None:
    """Rebuild the `entity_ruler` pipe from enabled rules if the ruler is dirty.

    No-op (and no DB read) when clean. On dirty, removes any existing ruler pipe,
    re-adds it after the stock `ner`, and loads the current enabled patterns. The
    dirty flag is cleared only after a successful rebuild, so a failed rebuild
    leaves the ruler dirty and retries on the next call.
    """
    global _dirty
    with _dirty_lock:
        if not _dirty:
            return

    async with unit_of_work(engine) as uow:
        rules = await uow.entity_rules.list_enabled()

    patterns = compile_pattern_dicts(rules)
    if nlp.has_pipe(ENTITY_RULER_PIPE):
        nlp.remove_pipe(ENTITY_RULER_PIPE)
    ruler = nlp.add_pipe(ENTITY_RULER_PIPE, config=_ENTITY_RULER_CONFIG)
    ruler.add_patterns(patterns)

    with _dirty_lock:
        _dirty = False
