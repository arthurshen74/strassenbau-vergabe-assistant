"""Content-based form detection.

Having an `/AcroForm` dictionary does not make a PDF a form: plans, Gutachten and
flattened Formblätter often carry one with zero fields. A PDF is a form when it embeds
an XFA packet, or when its AcroForm has at least FORM_MIN_FIELDS fillable fields.
"""

from __future__ import annotations

import io
import logging
from enum import StrEnum
from typing import Any

from pypdf import PdfReader

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


def detect_form_kind(pdf_bytes: bytes) -> FormKind | None:
    """XFA, AcroForm, or None for a PDF that is not a fillable form (or not parseable,
    in which case it takes the prose path)."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        acroform = reader.trailer[KEY_ROOT].get(KEY_ACROFORM) # type: ignore
        if acroform is None:
            return None
        if KEY_XFA in acroform.get_object():
            return FormKind.XFA
        fields = reader.get_fields() or {}
    except Exception:
        logger.warning("form detection failed, treating the PDF as prose")
        return None
    fillable = sum(1 for field in fields.values() if is_fillable(field))
    return FormKind.ACROFORM if fillable >= FORM_MIN_FIELDS else None


def is_fillable(field: Any) -> bool:
    """A field that carries a value: not a pushbutton, not a signature, and not a
    non-terminal node without a type."""
    field_type = field.get(KEY_FT)
    if field_type is None or field_type == FT_SIGNATURE:
        return False
    return not (field_type == FT_BUTTON and int(field.get(KEY_FF, 0)) & FLAG_PUSHBUTTON)
