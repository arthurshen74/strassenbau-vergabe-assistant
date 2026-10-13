from __future__ import annotations

from uuid import uuid4

from shared.services.ingestion.forms.flattened import extract_flattened, find_boxes
from tests.form_pdfs import (
    HVA_111_FOOTER,
    Box,
    Text,
    flattened_pdf,
    flattened_pdf_pages,
    hva_111_page,
)


def test_boxes_are_found_from_lines_and_rects_with_their_state() -> None:
    toggles = find_boxes(hva_111_page())

    assert [(round(t.bbox[0]), round(t.bbox[1]), t.checked) for t in toggles] == [
        (90, 112, True),
        (90, 127, False),
        (104, 142, False),
        (90, 204, True),
        (90, 219, False),
        (90, 262, False),
    ]
    assert {t.page for t in toggles} == {1}


def test_glyph_in_running_text_is_not_a_tick() -> None:
    pdf = flattened_pdf([Box(90, 700)], [Text(104.9, 702, "Textform x-beliebig")])
    assert [t.checked for t in find_boxes(pdf)] == [False]


def test_lines_and_fields_of_the_hva_excerpt() -> None:
    extraction = extract_flattened(hva_111_page(), uuid4())

    assert [line.line_text for line in extraction.lines] == [
        HVA_111_FOOTER,
        "## 4 Losweise Vergabe:",
        "[x] Nein",
        "[ ] Ja, Angebotsabgabe ist zugelassen",
        "[ ] nur für ein Los",
        "Fortsetzung der Option",
        "## 6 Nebenangebote",
        "[x] 6.1 Nebenangebote sind nicht zugelassen",
        "[ ] 6.2 Nebenangebote sind zugelassen",
        "## 7 Angebotswertung:",
        "[ ] Preis",
    ]
    assert [line.line_id for line in extraction.lines] == list(range(11))
    assert extraction.lines[7].bbox[0] == extraction.lines[6].bbox[0]  # number column
    assert (extraction.toggles, extraction.checked, extraction.unresolved) == (6, 2, 0)
    assert extraction.furniture == 0
    assert [(f.section, f.name, f.label, f.value) for f in extraction.fields] == [
        ("4 Losweise Vergabe:", "p1-0", "Nein", "ja"),
        ("4 Losweise Vergabe:", "p1-1", "Ja, Angebotsabgabe ist zugelassen", "nein"),
        ("4 Losweise Vergabe:", "p1-2", "nur für ein Los", "nein"),
        ("6 Nebenangebote", "p1-3", "6.1 Nebenangebote sind nicht zugelassen", "ja"),
        ("6 Nebenangebote", "p1-4", "6.2 Nebenangebote sind zugelassen", "nein"),
        ("7 Angebotswertung:", "p1-5", "Preis", "nein"),
    ]
    assert [f.field_order for f in extraction.fields] == list(range(6))


def test_box_without_printed_line_is_unresolved() -> None:
    pdf = flattened_pdf(
        [Box(62, 700), Box(62, 680, checked=True)], [Text(90.7, 682, "Anlage")]
    )
    extraction = extract_flattened(pdf, uuid4())

    assert [line.line_text for line in extraction.lines] == ["## Seite 1", "[x] Anlage"]
    assert (extraction.toggles, extraction.checked, extraction.unresolved) == (2, 1, 1)


def test_footer_repeats_are_dropped_and_do_not_break_nesting() -> None:
    def footer(page: int) -> list[Text]:
        return [Text(62, 50, HVA_111_FOOTER, 8), Text(504, 50, f"Seite {page}", 8)]

    pages = [
        ([], [Text(62, 750, "1"), Text(90.7, 750, "Kopf"), *footer(1)]),
        (
            [Box(90, 705)],
            [
                Text(62, 740, "5"),
                Text(90.7, 740, "Nebenangebote"),
                Text(104.9, 707, "Nebenangebote sind zugelassen"),
                Text(119, 120, "nur für nachfolgend genannte Bereiche"),
                *footer(2),
            ],
        ),
        (
            [Box(90, 700, checked=True)],
            [
                Text(119, 780, "mit Ausnahme nachfolgend genannter Bereiche"),
                Text(62, 720, "6"),
                Text(90.7, 720, "Angebotswertung"),
                Text(104.9, 702, "Preis"),
                *footer(3),
            ],
        ),
    ]
    extraction = extract_flattened(flattened_pdf_pages(pages), uuid4())

    assert [line.line_text for line in extraction.lines] == [
        "## 1 Kopf",
        HVA_111_FOOTER,
        "Seite 1",
        "## 5 Nebenangebote",
        "[ ] Nebenangebote sind zugelassen",
        "nur für nachfolgend genannte Bereiche",
        "mit Ausnahme nachfolgend genannter Bereiche",
        "## 6 Angebotswertung",
        "[x] Preis",
    ]
    assert extraction.furniture == 4
    assert [line.page for line in extraction.lines] == [1, 1, 1, 2, 2, 2, 3, 3, 3]
