from __future__ import annotations

from shared.services.ingestion.forms.detect import FormKind, detect_form_kind
from tests.form_pdfs import (
    FLAG_PUSHBUTTON,
    FieldSpec,
    acroform_pdf,
    text_field,
    three_field_form,
)


def test_acroform_without_fields_is_not_a_form() -> None:
    assert detect_form_kind(acroform_pdf([])) is None


def test_two_fields_are_not_a_form() -> None:
    pdf = acroform_pdf([text_field("a", 700, "1"), text_field("b", 680, "2")])
    assert detect_form_kind(pdf) is None


def test_three_fields_are_an_acroform() -> None:
    assert detect_form_kind(three_field_form()) is FormKind.ACROFORM


def test_pushbuttons_do_not_count() -> None:
    pdf = acroform_pdf(
        [
            text_field("a", 700, "1"),
            text_field("b", 680, "2"),
            FieldSpec("Drucken", "/Btn", (50, 600, 100, 620), flags=FLAG_PUSHBUTTON),
        ]
    )
    assert detect_form_kind(pdf) is None


def test_xfa_entry_is_xfa() -> None:
    assert detect_form_kind(acroform_pdf([], xfa=True)) is FormKind.XFA


def test_garbage_is_not_a_form() -> None:
    assert detect_form_kind(b"not a pdf at all") is None
