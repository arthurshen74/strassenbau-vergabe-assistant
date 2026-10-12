"""Form detection and role over the training corpus (server/training, gitignored).

Regression test for the "AcroForm dict with zero fields" trap: plans, Gutachten and the
LV print PDFs carry an /AcroForm dictionary without fields and must stay prose, while a
zero-field Formblatt with a printed footer or filename token is a flattened form.
Skipped when the corpus is not checked out."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import pytest

from shared.models.enums import DocumentType, FormRole
from shared.services.ingestion.classify import classify_document
from shared.services.ingestion.forms.detect import FormKind, detect_form_kind
from shared.services.ingestion.forms.identify import identify_formblatt
from shared.services.ingestion.forms.role import FormFamily

CORPUS = Path(__file__).resolve().parents[3] / "server" / "training"

pytestmark = pytest.mark.skipif(
    not CORPUS.is_dir(), reason="training corpus not present"
)

EXPECTED_UNBEKANNT = {
    "04 Baustelleninformationsschild.pdf",
    "Informationspflicht zur Nachprüfung nach 14 ThürVgG.pdf",
    "TTSiB Projektdatenblatt FG231.pdf",
}


def test_corpus_forms_and_roles() -> None:
    logging.disable(logging.WARNING)
    kinds: Counter[FormKind] = Counter()
    roles: Counter[FormRole] = Counter()
    unbekannt: set[str] = set()
    prose_forms: list[str] = []
    wrong_111: list[str] = []
    try:
        for pdf in sorted(CORPUS.rglob("*")):
            if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
                continue
            data = pdf.read_bytes()
            content_id = identify_formblatt(data)
            kind = detect_form_kind(data, pdf.name, content_id)
            if content_id == (FormFamily.HVA_B_STB, "111"):
                classification = classify_document(pdf.name, data)
                if (
                    classification.document_type is not DocumentType.FORM_DOCUMENT
                    or classification.form_id != "HVA B-StB 111"
                ):
                    wrong_111.append(pdf.name)
            if kind is None:
                continue
            kinds[kind] += 1
            role = classify_document(pdf.name, data).form_role
            roles[role] += 1
            if role is FormRole.UNBEKANNT:
                unbekannt.add(pdf.name)
            if pdf.name.startswith("LV Los") or "Baubeschreibung" in pdf.name:
                prose_forms.append(pdf.name)
    finally:
        logging.disable(logging.NOTSET)

    assert kinds == {FormKind.ACROFORM: 80, FormKind.XFA: 12, FormKind.FLATTENED: 92}
    assert unbekannt == EXPECTED_UNBEKANNT
    assert prose_forms == []
    assert wrong_111 == []
