"""End-to-end EntityRuler pipeline against the real de_core_news_lg model and DB.

The ruler pipe is added to the shared spaCy singleton, so each test cleans the
entity_rules table and restores the singleton (removes the ruler pipe, marks dirty)
on teardown to stay isolated from the other NLP tests sharing that singleton.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.tables.entity_rules import entity_rules
from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import NewEntityRule
from shared.models.enums import BlockType
from shared.models.nlp import ReflowedBlock
from shared.services.nlp.analysis import analyze_blocks, get_nlp
from shared.services.nlp.entity_ruler import (
    ENTITY_RULER_PIPE,
    ensure_ruler_current,
    mark_dirty,
)


@pytest_asyncio.fixture
async def ruler_engine(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    async with engine.begin() as conn:
        await conn.execute(delete(entity_rules))
    mark_dirty()
    yield engine
    async with engine.begin() as conn:
        await conn.execute(delete(entity_rules))
    nlp = get_nlp()
    if nlp.has_pipe(ENTITY_RULER_PIPE):  # type: ignore[attr-defined]
        nlp.remove_pipe(ENTITY_RULER_PIPE)  # type: ignore[attr-defined]
    mark_dirty()


def _block(text: str) -> ReflowedBlock:
    return ReflowedBlock(
        block_id=0, block_type=BlockType.PROSE, text=text, page_start=1, page_end=1, line_ids=[0]
    )


async def test_ruler_overrides_stock_mispredict(ruler_engine: AsyncEngine) -> None:
    # "Magdeburg" is a reliable stock LOC; a BAUSTOFF rule over it must win.
    async with unit_of_work(ruler_engine) as uow:
        await uow.entity_rules.add(
            NewEntityRule(label="BAUSTOFF", pattern="Magdeburg", pattern_id="test_baustoff")
        )
    nlp = get_nlp()
    await ensure_ruler_current(nlp, ruler_engine)

    doc = nlp("Die Arbeiten in Magdeburg beginnen.")  # type: ignore[operator]
    magdeburg = next(e for e in doc.ents if e.text == "Magdeburg")
    assert magdeburg.label_ == "BAUSTOFF"
    assert magdeburg.ent_id_ == "test_baustoff"


async def test_disabled_rule_excluded(ruler_engine: AsyncEngine) -> None:
    async with unit_of_work(ruler_engine) as uow:
        await uow.entity_rules.add(
            NewEntityRule(label="BAUSTOFF", pattern="Magdeburg", enabled=False)
        )
    nlp = get_nlp()
    await ensure_ruler_current(nlp, ruler_engine)

    doc = nlp("Die Arbeiten in Magdeburg beginnen.")  # type: ignore[operator]
    magdeburg = next(e for e in doc.ents if e.text == "Magdeburg")
    assert magdeburg.label_ != "BAUSTOFF"  # disabled rule absent; stock label stands


async def test_provenance_rule_hit_vs_stock_guess(ruler_engine: AsyncEngine) -> None:
    async with unit_of_work(ruler_engine) as uow:
        await uow.entity_rules.add(
            NewEntityRule(label="BAUSTOFF", pattern="Magdeburg", pattern_id="test_baustoff")
        )
    nlp = get_nlp()
    await ensure_ruler_current(nlp, ruler_engine)

    _, _, entities, _ = analyze_blocks(
        [_block("Die Firma liefert nach Magdeburg und Berlin.")], [BlockType.PROSE]
    )
    occurrences = [occ for label in entities.labels for occ in label.occurrences]
    magdeburg = next(o for o in occurrences if o.text == "Magdeburg")
    assert magdeburg.pattern_id == "test_baustoff"  # rule-derived carries provenance

    berlin = next(o for o in occurrences if o.text == "Berlin")
    assert berlin.pattern_id is None  # stock-model guess, no rule provenance


async def test_ent_html_matches_entities_and_respects_include_blocks(
    ruler_engine: AsyncEngine,
) -> None:
    async with unit_of_work(ruler_engine) as uow:
        await uow.entity_rules.add(
            NewEntityRule(label="BAUSTOFF", pattern="Magdeburg", pattern_id="test_baustoff")
        )
    nlp = get_nlp()
    await ensure_ruler_current(nlp, ruler_engine)

    prose = ReflowedBlock(
        block_id=0,
        block_type=BlockType.PROSE,
        text="Die Firma liefert nach Magdeburg.",
        page_start=1,
        page_end=1,
        line_ids=[0],
    )
    excluded = ReflowedBlock(
        block_id=1,
        block_type=BlockType.HEADING,
        text="Ueberschrift Sonderposten",
        page_start=1,
        page_end=1,
        line_ids=[1],
    )
    _, _, entities, ent_html = analyze_blocks([prose, excluded], [BlockType.PROSE])

    # The BAUSTOFF occurrence shows in both the breakdown and the highlight render.
    baustoff = next(label for label in entities.labels if label.label == "BAUSTOFF")
    assert any(o.text == "Magdeburg" for o in baustoff.occurrences)
    assert "Magdeburg" in ent_html
    assert "BAUSTOFF" in ent_html
    # include_blocks filters the render too: the excluded HEADING never appears.
    assert "Sonderposten" not in ent_html
