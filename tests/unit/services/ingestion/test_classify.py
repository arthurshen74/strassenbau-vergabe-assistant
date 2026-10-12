from __future__ import annotations

import pytest
from shared.models.enums import DocumentType, FormRole
from shared.services.ingestion.classify import (
    LV_DOCUMENT,
    PROSE_DOCUMENT,
    DocumentClassification,
    classify_document,
)

from tests.form_pdfs import acroform_pdf, hva_111_page, three_field_form


@pytest.mark.parametrize(
    "file_name",
    ["anything.d83", "P22039_LV1.D83", "projekt_lv.x83", "P630394379990126_LV.X83"],
)
def test_gaeb_is_lv_regardless_of_bytes(file_name: str) -> None:
    assert classify_document(file_name, b"<GAEB/>") == LV_DOCUMENT


def test_prose_for_everything_else() -> None:
    # The LV print-layout PDF is prose too: LV items come from GAEB files only.
    assert classify_document("Projekt_LV1.pdf", b"%PDF") == PROSE_DOCUMENT
    assert classify_document("Projekt_LV1.txt", b"x") == PROSE_DOCUMENT
    assert classify_document("anhang.pdf", b"%PDF") == PROSE_DOCUMENT


def test_zero_field_acroform_is_prose() -> None:
    assert classify_document("LV Los 1-3.pdf", acroform_pdf([])) == PROSE_DOCUMENT


def test_form_bytes_without_pdf_suffix_are_prose() -> None:
    assert classify_document("T1.1 FB 312-B.bin", three_field_form()) == PROSE_DOCUMENT


def test_vergabestelle_form_has_role_and_id() -> None:
    result = classify_document("T1.1 FB 312-B Aufforderung.pdf", three_field_form())
    assert result == DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT,
        form_role=FormRole.VERGABESTELLE,
        form_id="FB 312-B",
    )


def test_bieter_form_has_role_and_id() -> None:
    result = classify_document(
        "T1.6 FB 331-B Angebotsschreiben.pdf", three_field_form()
    )
    assert result == DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT,
        form_role=FormRole.BIETER,
        form_id="FB 331-B",
    )


def test_unknown_form_has_no_id() -> None:
    result = classify_document("Baustelleninformationsschild.pdf", three_field_form())
    assert result == DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT,
        form_role=FormRole.UNBEKANNT,
        form_id=None,
    )


def test_flattened_form_is_identified_by_its_footer() -> None:
    result = classify_document("00 - Aufforderung zur Angebotsabgabe.pdf", hva_111_page())
    assert result == DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT,
        form_role=FormRole.VERGABESTELLE,
        form_id="HVA B-StB 111",
    )


def test_keyword_only_bieter_form_has_role_but_no_id() -> None:
    result = classify_document("Nachweis für Sicherungsarbeiten.pdf", three_field_form())
    assert result == DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT,
        form_role=FormRole.BIETER,
        form_id=None,
    )
