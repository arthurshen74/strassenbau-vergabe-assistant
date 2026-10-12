"""Tender and form PDF discovery over the extracted training corpus.

A tender is a directory of `server/training` (the `.json` and `.zip` siblings are
skipped). A form is any PDF under it that `detect_form_kind` recognises, or a
zero-field PDF whose filename carries a Formblatt id (then `flattened`). Vergabestelle
and UNBEKANNT forms sort first, Bieter forms last.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from uuid import uuid4

import pdfplumber
from pydantic import BaseModel, ConfigDict

from scripts.form_labeler.store import PdfKind
from shared.models.enums import FormRole
from shared.models.source_line import NewSourceLine
from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.forms.detect import detect_form_kind
from shared.services.ingestion.forms.role import classify_form_role

logger = logging.getLogger(__name__)

PDF_GLOB = "*.pdf"
STEM_SEPARATOR = "__"

ROLE_ORDER = {FormRole.VERGABESTELLE: 0, FormRole.UNBEKANNT: 1, FormRole.BIETER: 2}


class Tender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: Path


class FormPdf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender: str
    path: Path
    rel: str  # posix path relative to the tender directory, as stored in labels
    stem: str  # label file stem, unique within the tender
    role: FormRole
    form_id: str | None
    kind: PdfKind
    pages: int

    @property
    def is_bieter(self) -> bool:
        return self.role is FormRole.BIETER


def list_tenders(root: Path) -> list[Tender]:
    return [
        Tender(name=path.name, path=path)
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]


def list_forms(tender: Tender) -> list[FormPdf]:
    forms = [
        form
        for path in sorted(tender.path.rglob(PDF_GLOB))
        if (form := _classify(tender, path)) is not None
    ]
    forms.sort(key=lambda form: (ROLE_ORDER[form.role], form.rel))
    return _unique_stems(forms)


def form_kind(pdf_bytes: bytes, form_id: str | None) -> PdfKind | None:
    """The detected kind, `flattened` for a zero-field PDF with a Formblatt id, else
    None (not a form)."""
    detected = detect_form_kind(pdf_bytes)
    if detected is not None:
        return PdfKind(detected.value)
    return PdfKind.FLATTENED if form_id is not None else None


def page_lines(pdf_bytes: bytes, page: int) -> list[NewSourceLine]:
    """The pipeline's own lines of one page."""
    return [line for line in all_lines(pdf_bytes) if line.page == page]


def all_lines(pdf_bytes: bytes) -> list[NewSourceLine]:
    return extract_source_lines(pdf_bytes, uuid4())


def _classify(tender: Tender, path: Path) -> FormPdf | None:
    role, form_id = classify_form_role(path.name)
    pdf_bytes = path.read_bytes()
    kind = form_kind(pdf_bytes, form_id)
    if kind is None:
        return None
    return FormPdf(
        tender=tender.name,
        path=path,
        rel=path.relative_to(tender.path).as_posix(),
        stem=path.stem,
        role=role,
        form_id=form_id,
        kind=kind,
        pages=count_pages(pdf_bytes),
    )


def count_pages(pdf_bytes: bytes) -> int:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        logger.warning("page count failed, reporting 0 pages")
        return 0


def _unique_stems(forms: list[FormPdf]) -> list[FormPdf]:
    """Prefix the parent directory onto a stem that two PDFs of the tender share."""
    counts: dict[str, int] = {}
    for form in forms:
        counts[form.stem] = counts.get(form.stem, 0) + 1
    return [
        form.model_copy(
            update={"stem": f"{Path(form.rel).parent.name}{STEM_SEPARATOR}{form.stem}"}
        )
        if counts[form.stem] > 1
        else form
        for form in forms
    ]
