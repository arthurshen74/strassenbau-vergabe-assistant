"""Content-based form detection.

Having an `/AcroForm` dictionary does not make a PDF a form: plans, Gutachten and
flattened Formblätter often carry one with zero fields. A PDF is a form when it embeds
an XFA packet, when its AcroForm has at least FORM_MIN_FIELDS fillable fields, or, with
no fields at all, when its printed footer or filename token names a Formblatt of the
role table (a flattened form). A zero-field PDF without such an id takes the prose path.
"""

from __future__ import annotations

import io
import logging
from enum import StrEnum
from typing import Any

from pypdf import PdfReader

from shared.services.ingestion.forms.role import (
    FormFamily,
    _find_token,
    lookup_formblatt,
)

logger = logging.getLogger(__name__)

FORM_MIN_FIELDS = 3

KEY_ROOT = "/Root"
KEY_ACROFORM = "/AcroForm"
KEY_XFA = "/XFA"
KEY_FT = "/FT"
KEY_FF = "/Ff"
FT_BUTTON = "/Btn"
FT_SIGNATURE = "/Sig"
FLAG_PUSHBUTTON = 1 << 16
FLAG_RADIO = 1 << 15


class FormKind(StrEnum):
    XFA = "xfa"
    ACROFORM = "acroform"
    FLATTENED = "flattened"


def detect_form_kind(
    pdf_bytes: bytes, file_name: str, content_id: tuple[FormFamily, str] | None
) -> FormKind | None:
    """XFA, AcroForm, flattened, or None for a PDF that is not a form (or not
    parseable, in which case it takes the prose path). `content_id` is the footer id
    from `identify_formblatt`, computed once by the caller."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        acroform = reader.trailer[KEY_ROOT].get(KEY_ACROFORM)  # type: ignore
        if acroform is not None and KEY_XFA in acroform.get_object():
            return FormKind.XFA
        fields = reader.get_fields() or {}
    except Exception:  # noqa: BLE001 -- pypdf raises many types on malformed input
        logger.warning("form detection failed, treating the PDF as prose")
        return None
    fillable = sum(1 for field in fields.values() if is_fillable(field))
    if fillable >= FORM_MIN_FIELDS:
        return FormKind.ACROFORM
    if fillable == 0 and is_known_formblatt(file_name, content_id):
        return FormKind.FLATTENED
    return None


def is_known_formblatt(
    file_name: str, content_id: tuple[FormFamily, str] | None
) -> bool:
    """Whether the footer id or the filename token names a row of the role table."""
    for form_id in (content_id, _find_token(file_name)):
        if form_id is not None and lookup_formblatt(*form_id) is not None:
            return True
    return False


def is_fillable(field: Any) -> bool:
    """A field that carries a value: not a pushbutton, not a signature, and not a
    non-terminal node without a type."""
    field_type = field.get(KEY_FT)
    if field_type is None or field_type == FT_SIGNATURE:
        return False
    return not (field_type == FT_BUTTON and int(field.get(KEY_FF, 0)) & FLAG_PUSHBUTTON)
