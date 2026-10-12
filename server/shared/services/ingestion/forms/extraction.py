from __future__ import annotations

from uuid import UUID

from shared.services.ingestion.forms.acroform import extract_acroform
from shared.services.ingestion.forms.detect import FormKind
from shared.services.ingestion.forms.flattened import extract_flattened
from shared.services.ingestion.forms.model import FormExtraction
from shared.services.ingestion.forms.xfa import extract_xfa


def extract_form(
    pdf_bytes: bytes, document_uuid: UUID, kind: FormKind
) -> FormExtraction:
    """Source lines and form fields of a form, read the way its kind stores them."""
    if kind is FormKind.XFA:
        return extract_xfa(pdf_bytes, document_uuid)
    if kind is FormKind.FLATTENED:
        return extract_flattened(pdf_bytes, document_uuid)
    return extract_acroform(pdf_bytes, document_uuid)
