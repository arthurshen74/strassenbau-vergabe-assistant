"""Reflow golden tests: the cases observed in the layout spike
(nlp-playground/layout-spike), encoded as compact fixtures.

Geometry mimics the corpus: ~10pt line height, ~12.7pt pitch inside a paragraph,
~15pt+ gaps between paragraphs, furniture at the page top.
"""

from __future__ import annotations

from uuid import uuid4

from shared.models.enums import BlockType
from shared.models.nlp import LayoutRegion
from shared.models.source_line import SourceLine
from shared.services.nlp.layout import (
    LABEL_PAGE_FOOTER,
    LABEL_PAGE_HEADER,
    LABEL_SECTION_HEADER,
    LABEL_TABLE,
)
from shared.services.nlp.reflow import reflow_document

_DOC = uuid4()
_LINE_HEIGHT = 10.0
_PITCH = 12.7


def _line(line_id: int, page: int, y: float, text: str, x: float = 70.0) -> SourceLine:
    return SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=_DOC,
        line_id=line_id,
        page=page,
        bbox=(x, y, x + 400.0, y + _LINE_HEIGHT),
        line_text=text,
    )


def _page_of_prose(page: int, first_id: int, top: float = 100.0) -> list[SourceLine]:
    """Three plain lines forming one paragraph. Text must differ across pages after
    digit normalization, or the repetition heuristic would (correctly) flag it."""
    marker = chr(ord("A") + page)
    return [
        _line(
            first_id + i,
            page,
            top + i * _PITCH,
            f"Abschnitt {marker} beschreibt die {'erste zweite dritte'.split()[i]} Leistung.",
        )
        for i in range(3)
    ]


def test_repeated_letterhead_is_furniture_even_where_model_misses_it() -> None:
    # B 246a case: 'Seite - N -' repeats on every page; the model labels it on page 1 only.
    lines = []
    for page in range(1, 7):
        lines.append(_line(page * 10, page, 40.0, f"Seite - {page} -"))
        lines.extend(_page_of_prose(page, page * 10 + 1))
    regions = [LayoutRegion(page=1, label=LABEL_PAGE_HEADER, bbox=(60.0, 35.0, 480.0, 55.0))]

    result = reflow_document(lines, regions)

    for page in range(1, 7):
        assert result.line_types[page * 10] is BlockType.FURNITURE
    assert all(b.block_type is not BlockType.FURNITURE for b in result.blocks)


def test_roman_numeral_front_matter_is_furniture_via_model_labels() -> None:
    # Bruecke Nr. 6 case: 'Seite I' / 'Seite II' repeat nowhere (no digits), but the
    # model boxes them as page footers.
    lines = [
        *_page_of_prose(1, 1),
        _line(4, 1, 800.0, "Seite I"),
        *_page_of_prose(2, 5),
        _line(8, 2, 800.0, "Seite II"),
        *_page_of_prose(3, 9),
        *_page_of_prose(4, 12),
    ]
    regions = [
        LayoutRegion(page=1, label=LABEL_PAGE_FOOTER, bbox=(60.0, 795.0, 480.0, 815.0)),
        LayoutRegion(page=2, label=LABEL_PAGE_FOOTER, bbox=(60.0, 795.0, 480.0, 815.0)),
    ]

    result = reflow_document(lines, regions)

    assert result.line_types[4] is BlockType.FURNITURE
    assert result.line_types[8] is BlockType.FURNITURE
    assert result.line_types[1] is BlockType.PROSE


def test_justification_hyphen_dropped() -> None:
    lines = [
        _line(1, 1, 100.0, "Kennwerte der zur Verwendung gekom-"),
        _line(2, 1, 100.0 + _PITCH, "menen Bindemittel sind zu übergeben."),
    ]

    result = reflow_document(lines, [])

    assert result.blocks[0].text == (
        "Kennwerte der zur Verwendung gekommenen Bindemittel sind zu übergeben."
    )


def test_compound_hyphen_kept() -> None:
    lines = [
        _line(1, 1, 100.0, "Die Messung erfolgt mit dem SRT-"),
        _line(2, 1, 100.0 + _PITCH, "Pendel nach Vorschrift."),
    ]

    result = reflow_document(lines, [])

    assert result.blocks[0].text == "Die Messung erfolgt mit dem SRT-Pendel nach Vorschrift."


def test_sentence_spanning_page_break_merges() -> None:
    # L 40 page 8->9 case: paragraph ends mid-sentence, next page starts lowercase.
    lines = [
        _line(1, 8, 700.0, "Die Arbeiten sind mit den wesentlichen"),
        _line(2, 9, 100.0, "Angaben über den Baufortschritt zu dokumentieren."),
    ]

    result = reflow_document(lines, [])

    assert len(result.blocks) == 1
    assert result.blocks[0].page_start == 8
    assert result.blocks[0].page_end == 9
    assert result.blocks[0].text.startswith("Die Arbeiten")
    assert result.blocks[0].line_ids == [1, 2]


def test_paragraph_gap_splits_blocks() -> None:
    lines = [
        _line(1, 1, 100.0, "Erster Absatz Zeile eins."),
        _line(2, 1, 100.0 + _PITCH, "Erster Absatz Zeile zwei."),
        # 25pt gap: a paragraph break (threshold is 0.8 x pitch ~ 10.2).
        _line(3, 1, 100.0 + _PITCH + 25.0, "Zweiter Absatz beginnt hier."),
    ]

    result = reflow_document(lines, [])

    assert [b.line_ids for b in result.blocks] == [[1, 2], [3]]


def test_table_lines_isolated_and_headings_typed() -> None:
    lines = [
        _line(1, 1, 100.0, "3.12 Prüfungen und Nachweise"),
        _line(2, 1, 130.0, "Der Auftragnehmer hat Nachweise zu führen."),
        _line(3, 1, 200.0, "Baufeld"),
        _line(4, 1, 212.0, "2,5 cm"),
        _line(5, 1, 224.0, "AC 8 D S"),
        _line(6, 1, 300.0, "Nach der Tabelle folgt weiterer Text."),
    ]
    regions = [
        LayoutRegion(page=1, label=LABEL_SECTION_HEADER, bbox=(60.0, 95.0, 480.0, 115.0)),
        LayoutRegion(page=1, label=LABEL_TABLE, bbox=(60.0, 195.0, 480.0, 240.0)),
    ]

    result = reflow_document(lines, regions)

    types = [b.block_type for b in result.blocks]
    assert types == [BlockType.HEADING, BlockType.PROSE, BlockType.TABLE, BlockType.PROSE]
    table_block = result.blocks[2]
    assert table_block.line_ids == [3, 4, 5]
    assert result.line_types[4] is BlockType.TABLE


def test_uncovered_lines_fall_back_to_prose_never_dropped() -> None:
    lines = _page_of_prose(1, 1)

    result = reflow_document(lines, [])

    assert sum(len(b.line_ids) for b in result.blocks) == 3
    assert all(t is BlockType.PROSE for t in result.line_types.values())
