from __future__ import annotations

from uuid import uuid4

from shared.services.ingestion.forms.acroform import extract_acroform, read_toggles
from tests.form_pdfs import (
    FLAG_PUSHBUTTON,
    FieldSpec,
    Text,
    acroform_pdf,
    text_field,
)


def _form() -> bytes:
    return acroform_pdf(
        [
            FieldSpec(
                "Teilnahme", "/Btn", (50, 600, 60, 610), "/Yes", tool_tip="Teilnahme"
            ),
            text_field("Ort", 680, "Berlin"),
            FieldSpec("Drucken", "/Btn", (400, 800, 450, 820), flags=FLAG_PUSHBUTTON),
            FieldSpec(
                "Nebenangebote", "/Btn", (50, 580, 60, 590), "/Off", tool_tip="Neben"
            ),
            text_field("Vergabenummer", 700, "26/001", x=300),
            text_field("Leer", 650, ""),
        ],
        texts=[
            Text(62, 750, "1"),
            Text(90, 750, "Teilnahme am Verfahren"),
            Text(65, 602, "Teilnahme als Bietergemeinschaft"),
        ],
    )


def test_fields_exclude_pushbutton_and_empty_text_in_reading_order() -> None:
    extraction = extract_acroform(_form(), uuid4())

    assert [(f.name, f.value, f.label) for f in extraction.fields] == [
        ("Vergabenummer", "26/001", None),
        ("Ort", "Berlin", None),
        ("Teilnahme", "ja", "Teilnahme"),
        ("Nebenangebote", "nein", "Neben"),
    ]
    assert [f.field_order for f in extraction.fields] == [0, 1, 2, 3]
    assert {(f.section, f.page) for f in extraction.fields} == {("Seite 1", 1)}


def test_toggles_come_from_checkbox_widgets_only() -> None:
    toggles = read_toggles(_form())

    assert [(t.checked, t.label, t.bbox) for t in toggles] == [
        (True, "Teilnahme", (50.0, 232.0, 60.0, 242.0)),
        (False, "Neben", (50.0, 252.0, 60.0, 262.0)),
    ]


def test_widgets_attach_to_printed_lines_with_tooltip_fallback() -> None:
    extraction = extract_acroform(_form(), uuid4())

    texts = [line.line_text for line in extraction.lines]
    assert texts == [
        "## 1 Teilnahme am Verfahren",
        "[x] Teilnahme als Bietergemeinschaft",
        "[ ] Neben",
    ]
    assert [line.line_id for line in extraction.lines] == [0, 1, 2]
    assert (extraction.toggles, extraction.checked, extraction.unresolved) == (2, 1, 0)


def test_blank_page_gets_a_page_heading() -> None:
    extraction = extract_acroform(acroform_pdf(_form_fields_only()), uuid4())
    assert [line.line_text for line in extraction.lines] == [
        "## Seite 1",
        "[x] Teilnahme",
    ]


def _form_fields_only() -> list[FieldSpec]:
    return [
        FieldSpec(
            "Teilnahme", "/Btn", (50, 600, 60, 610), "/Yes", tool_tip="Teilnahme"
        ),
        text_field("Ort", 680, "Berlin"),
        text_field("Vergabenummer", 700, "26/001", x=300),
    ]
