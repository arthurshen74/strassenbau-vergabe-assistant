from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from shared.models.enums import SourceDocType
from shared.models.lv_item import LVItem
from shared.models.source_line import SourceLine
from shared.services.ingestion.chunking import (
    CHUNK_SIZE,
    SOURCE_DOC_FIELD_DOCUMENT,
    SOURCE_DOC_FIELD_LV_ITEM,
    chunk_document,
    chunk_form,
    chunk_lv_item,
)


def _line(
    line_id: int, page: int, text: str, x0: float | None = None
) -> SourceLine:
    return SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=uuid4(),
        line_id=line_id,
        page=page,
        bbox=(0, 0, 1, 1) if x0 is None else (x0, 10.0 * line_id, x0 + 100, 10.0 * line_id + 9),
        line_text=text,
    )


def _form_texts(lines: list[SourceLine]) -> list[str]:
    drafts = chunk_form(lines, project_uuid=uuid4(), document_uuid=uuid4())
    return [d.chunk_text for d in drafts]


def _lv_item(*, langtext: str, langtext_resolved: str | None) -> LVItem:
    return LVItem(
        lv_item_uuid=uuid4(),
        document_uuid=uuid4(),
        oz="1.1",
        kurztext="k",
        langtext=langtext,
        langtext_resolved=langtext_resolved,
        menge=Decimal("1"),
        einheit="m",
        stl_nr="21 109",
        source_lines=[],
        last_ingestion=datetime.now(UTC),
    )


def test_chunk_document_indexes_and_derives_pages() -> None:
    project, document = uuid4(), uuid4()
    lines = [_line(i, 1 if i < 3 else 2, f"line {i} " + "x" * 40) for i in range(6)]

    drafts = chunk_document(lines, project_uuid=project, document_uuid=document)

    assert drafts
    assert [d.chunk_index for d in drafts] == list(range(len(drafts)))
    for draft in drafts:
        assert draft.source_doc_type == SourceDocType.DOCUMENT
        assert draft.source_doc_field == SOURCE_DOC_FIELD_DOCUMENT
        assert draft.source_doc_uuid == document
        assert draft.project_uuid == project
        assert draft.oz is None and draft.stl_nr is None
    # The single small chunk spans both pages.
    assert drafts[0].source_doc_pages == [1, 2]


def test_chunk_lv_item_prefers_resolved_and_denormalizes_oz() -> None:
    item = _lv_item(langtext="VERBATIM", langtext_resolved="RESOLVED BODY " + "y" * 40)

    drafts = chunk_lv_item(item, pages=[2, 3], project_uuid=uuid4())

    assert drafts
    assert "RESOLVED" in drafts[0].chunk_text and "VERBATIM" not in drafts[0].chunk_text
    for draft in drafts:
        assert draft.source_doc_type == SourceDocType.LV_ITEM
        assert draft.source_doc_field == SOURCE_DOC_FIELD_LV_ITEM
        assert draft.source_doc_uuid == item.lv_item_uuid
        assert draft.oz == "1.1" and draft.stl_nr == "21 109"
        assert draft.source_doc_pages == [2, 3]


def test_chunk_lv_item_falls_back_to_langtext_when_unresolved() -> None:
    item = _lv_item(langtext="ONLY VERBATIM TEXT", langtext_resolved=None)

    drafts = chunk_lv_item(item, pages=[1], project_uuid=uuid4())

    assert "ONLY VERBATIM TEXT" in drafts[0].chunk_text


def test_chunk_form_starts_a_chunk_at_each_heading() -> None:
    project, document = uuid4(), uuid4()
    lines = [
        _line(0, 1, "Formblatt 312-B"),
        _line(1, 1, "## Kopf"),
        _line(2, 1, "Vergabenummer: 26/001"),
        _line(3, 1, "## Leer"),
        _line(4, 2, "## Anlagen"),
        _line(5, 2, "Teilnahmebedingungen: ja"),
    ]

    drafts = chunk_form(lines, project_uuid=project, document_uuid=document)

    assert [d.chunk_text for d in drafts] == [
        "Formblatt 312-B",
        "## Kopf\nVergabenummer: 26/001",
        "## Anlagen\nTeilnahmebedingungen: ja",
    ]
    assert [d.chunk_index for d in drafts] == [0, 1, 2]
    assert [d.source_doc_pages for d in drafts] == [[1], [1], [2]]
    assert {d.source_doc_type for d in drafts} == {SourceDocType.FORM}
    assert {d.source_doc_field for d in drafts} == {SOURCE_DOC_FIELD_DOCUMENT}
    assert {d.source_doc_uuid for d in drafts} == {document}


def test_chunk_form_continues_a_long_section_under_its_heading() -> None:
    body = [_line(i, 1 + i // 4, f"Feld {i}: " + "x" * 290) for i in range(1, 9)]
    lines = [_line(0, 1, "## Anlagen"), *body]

    drafts = chunk_form(lines, project_uuid=uuid4(), document_uuid=uuid4())

    assert len(drafts) > 1
    assert all(d.chunk_text.startswith("## Anlagen\n") for d in drafts)
    assert all(len(d.chunk_text) <= CHUNK_SIZE for d in drafts)
    # Every body line lands whole in exactly one chunk.
    emitted = [
        text for d in drafts for text in d.chunk_text.split("\n")[1:]
    ]
    assert emitted == [line.line_text for line in body]
    assert drafts[0].source_doc_pages == [1]


def test_chunk_form_keeps_an_overlong_line_whole() -> None:
    long_line = "Hinweis: " + "y" * (CHUNK_SIZE + 50)
    lines = [_line(0, 1, "## Kopf"), _line(1, 1, long_line), _line(2, 1, "Ort: Berlin")]

    drafts = chunk_form(lines, project_uuid=uuid4(), document_uuid=uuid4())

    assert [d.chunk_text for d in drafts] == [
        f"## Kopf\n{long_line}",
        "## Kopf\nOrt: Berlin",
    ]


def test_chunk_form_drops_unchecked_options_and_what_is_nested_under_them() -> None:
    lines = [
        _line(0, 1, "## 4 Losweise Vergabe:", 62.4),
        _line(1, 1, "[x] Nein", 104.9),
        _line(2, 1, "[ ] Ja, Angebotsabgabe ist zugelassen", 104.9),
        _line(3, 1, "[ ] nur für ein Los", 119.1),
        _line(4, 1, "[x] für ein oder mehrere Lose", 119.1),
        _line(5, 1, "Fortsetzung der Option", 104.9),
        _line(6, 1, "Allgemeiner Hinweis zur Losvergabe", 90.7),
        _line(7, 1, "## 5 Mehrere Hauptangebote", 62.4),
        _line(8, 1, "Die Abgabe von mehr als einem Hauptangebot ist", 90.7),
        _line(9, 1, "[ ] zugelassen. Werden mehrere Hauptangebote abgegeben,", 104.9),
        _line(10, 1, "zuschlagsfähig sein.", 104.9),
        _line(11, 1, "[x] nicht zugelassen.", 92.1),
        _line(12, 2, "[ ] 6.2 Nebenangebote sind zugelassen", 62.4),
        _line(13, 2, "111 HVA B-StB Vorlage 03-23", 62.4),
        _line(14, 2, "Nebenangebote, die ausschließlich Preisnachlässe", 104.9),
        _line(15, 2, "## 7 Angebotswertung:", 62.4),
        _line(16, 2, "[ ] Preis", 104.9),
        _line(17, 2, "[ ] Mehrere Zuschlagskriterien", 104.9),
    ]

    assert _form_texts(lines) == [
        "## 4 Losweise Vergabe:\nNein\nAllgemeiner Hinweis zur Losvergabe",
        "## 5 Mehrere Hauptangebote\nDie Abgabe von mehr als einem Hauptangebot ist\n"
        "nicht zugelassen.",
        "## 7 Angebotswertung:\nkeine Option angekreuzt",
    ]


def test_chunk_form_without_geometry_drops_only_the_unchecked_line() -> None:
    lines = [
        _line(0, 1, "## Anlagen"),
        _line(1, 1, "Hinweis:"),
        _line(2, 1, "[ ] Teilnahmebedingungen"),
        _line(3, 1, "[x] Gewichtung"),
        _line(4, 1, "Einreichungsdatum: 2026-10-15"),
    ]

    assert _form_texts(lines) == [
        "## Anlagen\nHinweis:\nGewichtung\nEinreichungsdatum: 2026-10-15"
    ]


def test_chunk_form_empty_section_marker_has_the_heading_page() -> None:
    lines = [_line(0, 2, "## 7 Angebotswertung:", 62.4), _line(1, 2, "[ ] Preis", 104.9)]
    drafts = chunk_form(lines, project_uuid=uuid4(), document_uuid=uuid4())

    assert [(d.chunk_text, d.source_doc_pages) for d in drafts] == [
        ("## 7 Angebotswertung:\nkeine Option angekreuzt", [2])
    ]


def test_chunk_form_headingless_lines_before_the_first_section_collapse_too() -> None:
    lines = [
        _line(0, 1, "[ ] Vorab", 90.0),
        _line(1, 1, "nested", 100.0),
        _line(2, 1, "[x] Kopf", 90.0),
    ]
    assert _form_texts(lines) == ["Kopf"]
