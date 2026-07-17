"""Analysis and render tests against the real de_core_news_lg pipeline.

The model is a project dependency; first test in the module pays the load once.
"""

from __future__ import annotations

import pytest

from shared.models.enums import BlockType, RenderStyle
from shared.models.nlp import ReflowedBlock
from shared.services.nlp import render as render_module
from shared.services.nlp.analysis import analyze_blocks, sentence_hash
from shared.services.nlp.render import render_cache_key, render_dep_svg, render_ent_html


def _block(block_id: int, block_type: BlockType, text: str) -> ReflowedBlock:
    return ReflowedBlock(
        block_id=block_id,
        block_type=block_type,
        text=text,
        page_start=1,
        page_end=1,
        line_ids=[block_id],
    )


BLOCKS = [
    _block(0, BlockType.HEADING, "3.12 Prüfungen und Nachweise"),
    _block(
        1,
        BlockType.PROSE,
        "Der Auftragnehmer hat Bautagesberichte zu führen. "
        "Sie müssen alle Angaben enthalten.",
    ),
    _block(2, BlockType.TABLE, "Baufeld 2,5 cm AC 8 D S"),
]


def test_include_list_filters_blocks() -> None:
    sentences, pos = analyze_blocks(BLOCKS, [BlockType.PROSE, BlockType.HEADING])

    block_ids = {s.block_id for s in sentences}
    assert block_ids == {0, 1}
    assert len([s for s in sentences if s.block_id == 1]) == 2
    assert pos.token_count > 0


def test_tables_opt_in() -> None:
    sentences, _ = analyze_blocks(BLOCKS, [BlockType.TABLE])

    assert {s.block_id for s in sentences} == {2}


def test_pos_aggregation_sums_and_drill_down() -> None:
    _, pos = analyze_blocks(BLOCKS, [BlockType.PROSE])

    assert sum(t.count for t in pos.ud) == pos.token_count
    assert sum(t.count for t in pos.stts) == pos.token_count
    nouns = next(t for t in pos.ud if t.tag == "NOUN")
    assert any(tok.text == "Bautagesberichte" for tok in nouns.tokens)
    assert all(tok.lemma for tok in nouns.tokens)


def test_percentages_normalized() -> None:
    _, pos = analyze_blocks(BLOCKS, [BlockType.PROSE, BlockType.HEADING])

    assert sum(t.percentage for t in pos.ud) == pytest.approx(100.0, abs=1.0)


def test_sentence_hash_is_model_scoped_and_text_scoped() -> None:
    assert sentence_hash("Ein Satz.") == sentence_hash("Ein Satz.")
    assert sentence_hash("Ein Satz.") != sentence_hash("Ein anderer Satz.")


def test_render_cache_key_changes_with_model_version(monkeypatch: pytest.MonkeyPatch) -> None:
    key_before = render_cache_key(RenderStyle.DEP, "Ein Satz.")
    monkeypatch.setattr(render_module, "spacy_model_version", lambda: "de_core_news_lg-99.0.0")
    key_after = render_cache_key(RenderStyle.DEP, "Ein Satz.")

    assert key_before != key_after


def test_dep_render_is_svg() -> None:
    svg = render_dep_svg("Der Bieter kalkuliert seine Einheitspreise.")

    assert svg.lstrip().startswith("<svg")


def test_ent_render_is_html_with_entities() -> None:
    html = render_ent_html("Die LSBB Sachsen-Anhalt prüft die Baumaßnahme in Magdeburg.")

    assert "<svg" not in html
    assert "div" in html
    assert "Magdeburg" in html
