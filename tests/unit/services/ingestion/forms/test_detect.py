from __future__ import annotations

from shared.services.ingestion.forms.detect import FormKind, detect_form_kind
from shared.services.ingestion.forms.role import FormFamily
from tests.form_pdfs import (
    FLAG_PUSHBUTTON,
    FieldSpec,
    Text,
    acroform_pdf,
    flattened_pdf,
    hva_111_page,
    text_field,
    three_field_form,
)

HVA_111 = (FormFamily.HVA_B_STB, "111")


def test_acroform_without_fields_or_id_is_not_a_form() -> None:
    assert detect_form_kind(acroform_pdf([]), "LV Los 1-3.pdf", None) is None


def test_two_fields_are_not_a_form() -> None:
    pdf = acroform_pdf([text_field("a", 700, "1"), text_field("b", 680, "2")])
    assert detect_form_kind(pdf, "x.pdf", None) is None


def test_three_fields_are_an_acroform() -> None:
    assert detect_form_kind(three_field_form(), "x.pdf", None) is FormKind.ACROFORM


def test_acroform_with_footer_stays_acroform() -> None:
    assert detect_form_kind(three_field_form(), "x.pdf", HVA_111) is FormKind.ACROFORM


def test_pushbuttons_do_not_count() -> None:
    pdf = acroform_pdf(
        [
            text_field("a", 700, "1"),
            text_field("b", 680, "2"),
            FieldSpec("Drucken", "/Btn", (50, 600, 100, 620), flags=FLAG_PUSHBUTTON),
        ]
    )
    assert detect_form_kind(pdf, "x.pdf", None) is None


def test_xfa_entry_is_xfa() -> None:
    assert detect_form_kind(acroform_pdf([], xfa=True), "x.pdf", None) is FormKind.XFA


def test_zero_fields_with_footer_id_is_flattened() -> None:
    assert detect_form_kind(hva_111_page(), "00 - Aufforderung.pdf", HVA_111) is (
        FormKind.FLATTENED
    )


def test_zero_fields_with_filename_token_is_flattened() -> None:
    pdf = flattened_pdf([], [Text(62, 800, "Baubeschreibung")])
    assert detect_form_kind(pdf, "HVA_B_StB_111_Vorlage.pdf", None) is (
        FormKind.FLATTENED
    )


def test_zero_fields_without_table_row_is_prose() -> None:
    pdf = flattened_pdf([], [Text(62, 800, "Baubeschreibung")])
    assert detect_form_kind(pdf, "Baubeschreibung.pdf", None) is None
    assert detect_form_kind(pdf, "HVA_B_StB_199_Sonstiges.pdf", None) is None
    assert detect_form_kind(pdf, "x.pdf", (FormFamily.HVA_B_STB, "371")) is None
    assert detect_form_kind(pdf, "Eigenerklärung.pdf", None) is None


def test_two_fields_with_id_are_prose() -> None:
    pdf = acroform_pdf([text_field("a", 700, "1"), text_field("b", 680, "2")])
    assert detect_form_kind(pdf, "HVA_B_StB_111.pdf", HVA_111) is None


def test_garbage_is_not_a_form() -> None:
    assert detect_form_kind(b"not a pdf at all", "x.pdf", None) is None
