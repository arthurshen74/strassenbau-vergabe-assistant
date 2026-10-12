from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfWriter

from scripts.form_labeler.corpus import Tender, form_kind, list_forms, list_tenders
from scripts.form_labeler.store import PdfKind
from shared.models.enums import FormRole
from tests.form_pdfs import acroform_pdf, three_field_form


def _plain_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_flattened_rule_needs_a_form_id() -> None:
    assert form_kind(_plain_pdf(), "HVA B-StB 111") is PdfKind.FLATTENED
    assert form_kind(acroform_pdf([]), "HVA B-StB 111") is PdfKind.FLATTENED
    assert form_kind(_plain_pdf(), None) is None
    assert form_kind(three_field_form(), None) is PdfKind.ACROFORM
    assert form_kind(acroform_pdf([], xfa=True), None) is PdfKind.XFA


def test_list_forms_orders_vergabestelle_first_and_skips_plans(tmp_path: Path) -> None:
    tender_dir = tmp_path / "T1"
    (tender_dir / "sub").mkdir(parents=True)
    (tender_dir / "HVA_B_StB_121_x.pdf").write_bytes(three_field_form())
    (tender_dir / "Plan_1.pdf").write_bytes(_plain_pdf())
    (tender_dir / "sub" / "HVA_B_StB_111_x.pdf").write_bytes(_plain_pdf())
    (tender_dir / "Sonstiges.pdf").write_bytes(three_field_form())
    (tmp_path / "T1.zip").write_bytes(b"")

    tenders = list_tenders(tmp_path)
    assert [t.name for t in tenders] == ["T1"]
    forms = list_forms(tenders[0])

    assert [(f.rel, f.role, f.kind, f.pages) for f in forms] == [
        ("sub/HVA_B_StB_111_x.pdf", FormRole.VERGABESTELLE, PdfKind.FLATTENED, 1),
        ("Sonstiges.pdf", FormRole.UNBEKANNT, PdfKind.ACROFORM, 1),
        ("HVA_B_StB_121_x.pdf", FormRole.BIETER, PdfKind.ACROFORM, 1),
    ]
    assert forms[0].form_id == "HVA B-StB 111"


def test_duplicate_stems_get_the_parent_directory(tmp_path: Path) -> None:
    tender_dir = tmp_path / "T1"
    for folder in ("a", "b"):
        (tender_dir / folder).mkdir(parents=True)
        (tender_dir / folder / "FB 317-B.pdf").write_bytes(_plain_pdf())
    forms = list_forms(Tender(name="T1", path=tender_dir))
    assert [f.stem for f in forms] == ["a__FB 317-B", "b__FB 317-B"]
