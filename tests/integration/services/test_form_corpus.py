"""Form detection and role over the training corpus (server/training, gitignored).

Regression test for the "AcroForm dict with zero fields" trap: plans, Gutachten and the
LV print PDFs carry an /AcroForm dictionary without fields and must stay prose. Skipped
when the corpus is not checked out."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import pytest

from shared.models.enums import FormRole
from shared.services.ingestion.forms.detect import FormKind, detect_form_kind
from shared.services.ingestion.forms.role import classify_form_role

CORPUS = Path(__file__).resolve().parents[3] / "server" / "training"

pytestmark = pytest.mark.skipif(
    not CORPUS.is_dir(), reason="training corpus not present"
)


def test_corpus_forms_and_roles() -> None:
    logging.disable(logging.WARNING)
    try:
        kinds: Counter[FormKind] = Counter()
        roles: Counter[FormRole] = Counter()
        lv_print_forms: list[str] = []
        for pdf in sorted(CORPUS.rglob("*")):
            if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
                continue
            kind = detect_form_kind(pdf.read_bytes())
            if kind is None:
                continue
            kinds[kind] += 1
            roles[classify_form_role(pdf.name)[0]] += 1
            if pdf.name.startswith("LV Los"):
                lv_print_forms.append(pdf.name)
    finally:
        logging.disable(logging.NOTSET)

    assert kinds == {FormKind.ACROFORM: 80, FormKind.XFA: 12}
    assert roles[FormRole.UNBEKANNT] == 3
    assert lv_print_forms == []
