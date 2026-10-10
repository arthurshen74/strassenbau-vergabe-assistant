from __future__ import annotations

from uuid import uuid4

from shared.services.ingestion.forms.acroform import extract_acroform
from tests.form_pdfs import FLAG_PUSHBUTTON, FieldSpec, acroform_pdf, text_field


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
        ]
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


def test_lines_get_page_heading_and_checkbox_lines() -> None:
    extraction = extract_acroform(_form(), uuid4())

    texts = [line.line_text for line in extraction.lines]
    assert texts[0] == "## Seite 1"
    assert texts[-2:] == ["Teilnahme: ja", "Neben: nein"]
    assert [line.line_id for line in extraction.lines] == list(range(len(texts)))
