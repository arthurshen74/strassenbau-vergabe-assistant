from __future__ import annotations

from uuid import UUID, uuid4

from shared.models.source_line import NewSourceLine
from shared.services.ingestion.forms.model import Toggle
from shared.services.ingestion.forms.toggles import (
    TOGGLE_Y_TOLERANCE,
    attach_toggles,
    finish_form_lines,
    insert_headings,
    merge_marginal_tokens,
    option_fields,
)

DOC = uuid4()
LABEL_X0 = 104.9
BOX = (89.9, 483.8, 100.1, 493.7)
NESTED_BOX = (104.0, 537.1, 114.2, 547.0)


def _line(
    text: str,
    x0: float,
    y0: float,
    x1: float | None = None,
    y1: float | None = None,
    *,
    page: int = 1,
    document_uuid: UUID = DOC,
) -> NewSourceLine:
    return NewSourceLine(
        document_uuid=document_uuid,
        line_id=0,
        page=page,
        bbox=(
            x0,
            y0,
            x1 if x1 is not None else x0 + 100,
            y1 if y1 is not None else y0 + 12.8,
        ),
        line_text=text,
    )


def _texts(lines: list[NewSourceLine]) -> list[str]:
    return [line.line_text for line in lines]


# --- merge_marginal_tokens ---------------------------------------------------


def test_section_number_is_prefixed_and_bbox_extended() -> None:
    label = _line("Nebenangebote sind nicht zugelassen", LABEL_X0, 482.3, 468.2)
    merged = merge_marginal_tokens([_line("6.1", 62.4, 482.3, 76.3), label])

    assert _texts(merged) == ["6.1 Nebenangebote sind nicht zugelassen"]
    assert merged[0].bbox == (62.4, 482.3, 468.2, 495.1)


def test_tick_glyph_is_dropped() -> None:
    merged = merge_marginal_tokens(
        [_line("X", 92.1, 484.0, 97.5, 494.3), _line("Nein", LABEL_X0, 482.3)]
    )
    assert _texts(merged) == ["Nein"]


def test_token_without_partner_is_kept() -> None:
    lines = [
        _line("X", 92.1, 484.0, 97.5),
        _line("Nein", LABEL_X0, 520.0),
        _line("left of it", 30.0, 484.0, 80.0),
        _line("5", 62.4, 700.0, 67.9, page=2),
    ]
    assert _texts(merge_marginal_tokens(lines)) == _texts(lines)


def test_nearest_row_wins_and_glyph_does_not_take_the_number() -> None:
    lines = [
        _line("6.1", 62.4, 482.3, 76.3),
        _line("X", 92.1, 484.0, 97.5),
        _line("6.2", 62.4, 508.9, 76.3),
        _line("Nebenangebote sind nicht zugelassen", LABEL_X0, 482.3),
        _line("Nebenangebote sind zugelassen", LABEL_X0, 508.9),
    ]
    assert _texts(merge_marginal_tokens(lines)) == [
        "6.1 Nebenangebote sind nicht zugelassen",
        "6.2 Nebenangebote sind zugelassen",
    ]


# --- attach_toggles ------------------------------------------------------------


def test_toggle_marks_the_line_right_of_the_box() -> None:
    lines = [_line("Nein", LABEL_X0, 482.3), _line("Ja", LABEL_X0, 508.9)]
    toggles = [
        Toggle(page=1, bbox=BOX, checked=True),
        Toggle(page=1, bbox=(89.9, 510.5, 100.1, 520.3), checked=False),
    ]

    attached, unresolved = attach_toggles(lines, toggles, DOC)

    assert _texts(attached) == ["[x] Nein", "[ ] Ja"]
    assert unresolved == 0
    assert [line.line_id for line in attached] == [0, 1]


def test_merged_glyph_and_number_lines_attach_and_lose_the_glyph() -> None:
    lines = [
        _line("X nicht zugelassen.", 92.1, 444.3, 182.1),
        _line("6.1 Nebenangebote sind nicht zugelassen", 62.4, 482.3, 468.2),
    ]
    toggles = [
        Toggle(page=1, bbox=(89.9, 445.8, 100.1, 455.7), checked=True),
        Toggle(page=1, bbox=BOX, checked=True),
    ]

    attached, _ = attach_toggles(lines, toggles, DOC)

    assert _texts(attached) == [
        "[x] nicht zugelassen.",
        "[x] 6.1 Nebenangebote sind nicht zugelassen",
    ]


def test_fallback_label_and_unresolved_count() -> None:
    lines = [_line("Far away", 400.0, 482.3)]
    toggles = [
        Toggle(page=1, bbox=BOX, checked=False, label="Neben"),
        Toggle(page=1, bbox=(89.9, 600.0, 100.1, 610.0), checked=True),
    ]

    attached, unresolved = attach_toggles(lines, toggles, DOC)

    assert _texts(attached) == ["Far away", "[ ] Neben"]
    assert attached[1].bbox == BOX
    assert unresolved == 1


def test_row_tolerance_boundary() -> None:
    centre = (BOX[1] + BOX[3]) / 2
    inside = _line("inside", LABEL_X0, centre + TOGGLE_Y_TOLERANCE - 0.1 - 6.4)
    outside = _line("outside", LABEL_X0, centre + TOGGLE_Y_TOLERANCE + 0.1 - 6.4)

    attached, unresolved = attach_toggles(
        [outside], [Toggle(page=1, bbox=BOX, checked=True)], DOC
    )
    assert _texts(attached) == ["outside"] and unresolved == 1

    attached, unresolved = attach_toggles(
        [inside], [Toggle(page=1, bbox=BOX, checked=True)], DOC
    )
    assert _texts(attached) == ["[x] inside"] and unresolved == 0


def test_three_boxes_in_one_row_each_take_their_own_label() -> None:
    # HVA 111 page 4: `X in Textform, | X mit fortgeschrittener/m ... | X mit ...`
    lines = [
        _line("X in Textform,", 92.1, 501.4, 154.8),
        _line("X mit fortgeschrittener/m Signatur/Siegel,", 177.2, 501.4, 359.8),
        _line("X mit qualifizierter/m Signatur/Siegel.", 375.6, 501.4, 539.9),
    ]
    row = (502.9, 512.7)
    toggles = [
        Toggle(page=1, bbox=(89.9, row[0], 100.1, row[1]), checked=True),
        Toggle(page=1, bbox=(175.0, row[0], 185.2, row[1]), checked=True),
        Toggle(page=1, bbox=(373.4, row[0], 383.6, row[1]), checked=True),
    ]

    attached, unresolved = attach_toggles(lines, toggles, DOC)

    assert _texts(attached) == [
        "[x] in Textform,",
        "[x] mit fortgeschrittener/m Signatur/Siegel,",
        "[x] mit qualifizierter/m Signatur/Siegel.",
    ]
    assert unresolved == 0


def test_lines_are_renumbered_in_reading_order() -> None:
    lines = [
        _line("second", 90.0, 300.0, page=1),
        _line("third", 90.0, 100.0, page=2),
        _line("first b", 200.0, 100.0, page=1),
        _line("first a", 90.0, 100.0, page=1),
    ]
    attached, _ = attach_toggles(lines, [], DOC)
    assert _texts(attached) == ["first a", "first b", "second", "third"]
    assert [line.line_id for line in attached] == [0, 1, 2, 3]


# --- insert_headings -------------------------------------------------------------


def test_numbered_headings_open_sections_and_pages_without_get_seite() -> None:
    lines = [
        _line("Kopf", 62.4, 100.0, page=1),
        _line("6 Nebenangebote", 62.4, 100.0, page=2),
        _line("6.1 Nebenangebote sind nicht zugelassen", 62.4, 120.0, page=2),
        _line("111 HVA B-StB Vorlage Aufforderung 03-23", 62.4, 785.1, page=2),
        _line("16540 Hohen Neuendorf", 62.4, 100.0, page=3),
        _line("[x] 3 Monate", 90.0, 120.0, page=3),
    ]
    headed = insert_headings(lines, DOC)

    assert _texts(headed) == [
        "## Seite 1",
        "Kopf",
        "## 6 Nebenangebote",
        "6.1 Nebenangebote sind nicht zugelassen",
        "111 HVA B-StB Vorlage Aufforderung 03-23",
        "## Seite 3",
        "16540 Hohen Neuendorf",
        "[x] 3 Monate",
    ]
    assert [line.line_id for line in headed] == list(range(8))
    assert headed[0].page == 1 and headed[5].page == 3


def test_numbered_line_in_the_text_column_is_not_a_heading() -> None:
    # HVA 131: `... hat dieser gemäß §` breaks before `11 VOB/B für jeden ...`.
    lines = [
        _line("2 Vertragsstrafen (§ 11 VOB/B)", 62.4, 158.8),
        _line("[ ] Vertragsstrafen werden vereinbart.", 119.1, 172.3),
        _line("11 VOB/B für jeden Werk- bzw. Kalendertag", 119.1, 198.3),
    ]
    assert _texts(insert_headings(lines, DOC)) == [
        "## 2 Vertragsstrafen (§ 11 VOB/B)",
        "[ ] Vertragsstrafen werden vereinbart.",
        "11 VOB/B für jeden Werk- bzw. Kalendertag",
    ]


# --- finish_form_lines + option_fields -------------------------------------------


def test_shared_tail_and_fields() -> None:
    lines = [
        _line("6", 62.4, 462.8, 67.9),
        _line("Nebenangebote", 90.7, 462.8),
        _line("6.1", 62.4, 482.3, 76.3),
        _line("X", 92.1, 484.0, 97.5),
        _line("Nebenangebote sind nicht zugelassen", LABEL_X0, 482.3),
        _line("für die gesamte Leistung", 119.1, 535.6),
    ]
    toggles = [
        Toggle(page=1, bbox=BOX, checked=True),
        Toggle(page=1, bbox=NESTED_BOX, checked=False),
    ]

    finished, unresolved = finish_form_lines(lines, toggles, DOC)

    assert _texts(finished) == [
        "## 6 Nebenangebote",
        "[x] 6.1 Nebenangebote sind nicht zugelassen",
        "[ ] für die gesamte Leistung",
    ]
    assert unresolved == 0
    assert [
        (f.section, f.name, f.label, f.value, f.page, f.field_order)
        for f in option_fields(finished, DOC)
    ] == [
        (
            "6 Nebenangebote",
            "p1-0",
            "6.1 Nebenangebote sind nicht zugelassen",
            "ja",
            1,
            0,
        ),
        ("6 Nebenangebote", "p1-1", "für die gesamte Leistung", "nein", 1, 1),
    ]
