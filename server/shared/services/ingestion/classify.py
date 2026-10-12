"""Decides what kind of document an upload is, before it is stored or enqueued.

`classify_document` is the single place that maps an upload (filename plus raw bytes) to
its `DocumentType` and, for a form, its Formblatt role and id. The rules apply in
precedence order:

1. A GAEB exchange file (D83/X83) is an LV document by definition, whatever its bytes.
2. A PDF that is a form (decided from its bytes by `detect_form_kind`: XFA, AcroForm,
   or a flattened Formblatt with a known id) is a form document; which Formblatt it is
   comes from the printed footer (`identify_formblatt`) or the filename token, and who
   fills it from the role table via `classify_form_role`.
3. Everything else is prose. This includes the LV print-layout PDF: LV items come from
   GAEB files only, so the printed LV must never become an LV document.

What happens to a document once classified (whether it is enqueued at all, how the
worker processes it) is decided by its consumers, not here. The worker reads the stored
type and never re-classifies. Form detection failures fall through to prose with a
warning (see `detect_form_kind`), which is the one silent fallback on this path.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.models.enums import DocumentType, FormRole
from shared.services.ingestion.forms.detect import detect_form_kind
from shared.services.ingestion.forms.identify import identify_formblatt
from shared.services.ingestion.forms.role import classify_form_role
from shared.services.ingestion.gaeb import (
    GAEB_D83_SUFFIX,
    GAEB_X83_SUFFIX,
    is_gaeb_lv_file,
)

PDF_SUFFIX = ".pdf"
INGESTIBLE_SUFFIXES = frozenset({PDF_SUFFIX, GAEB_D83_SUFFIX, GAEB_X83_SUFFIX})


class DocumentClassification(BaseModel):
    """What an upload is: its type and, for a form, who fills it and which Formblatt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type: DocumentType
    form_role: FormRole | None = None
    form_id: str | None = None


LV_DOCUMENT = DocumentClassification(document_type=DocumentType.LV_DOCUMENT)
PROSE_DOCUMENT = DocumentClassification(document_type=DocumentType.PROSE_DOCUMENT)


def classify_document(file_name: str, data: bytes) -> DocumentClassification:
    """Classify one upload by the precedence rules in the module docstring."""
    if is_gaeb_lv_file(file_name):
        return LV_DOCUMENT
    if not is_pdf_file_name(file_name):
        return PROSE_DOCUMENT
    content_id = identify_formblatt(data)
    if detect_form_kind(data, file_name, content_id) is None:
        return PROSE_DOCUMENT
    role, form_id = classify_form_role(file_name, content_id)
    return DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT, form_role=role, form_id=form_id
    )


def is_pdf_file_name(file_name: str) -> bool:
    return file_name.lower().endswith(PDF_SUFFIX)
