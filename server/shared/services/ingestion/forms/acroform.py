"""AcroForm extraction: poppler page text plus what it cannot see.

`pdftotext -bbox-layout` renders static text and text-field appearances with geometry,
so it stays the source of the page lines. It does not render checkbox or radio state in
a usable form; every such widget becomes a `Toggle` from its `/Rect` and `/AS` state and
is attached to the printed line next to it, with the `/TU` tooltip as the fallback label
when no printed line is there. The structured fields come from the field dictionaries
in reading order (page, top to bottom, left to right), one row per field.
"""

from __future__ import annotations

import io
from typing import Any, NamedTuple
from uuid import UUID

from pypdf import PdfReader
from pypdf.generic import NameObject

from shared.models.form_field import NewFormField
from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.forms.detect import (
    FLAG_PUSHBUTTON,
    FLAG_RADIO,
    FT_BUTTON,
    FT_SIGNATURE,
    KEY_FF,
    KEY_FT,
)
from shared.services.ingestion.forms.model import (
    CHECKED,
    UNCHECKED,
    FormExtraction,
    Toggle,
)
from shared.services.ingestion.forms.toggles import finish_form_lines, page_section

KEY_ANNOTS = "/Annots"
KEY_SUBTYPE = "/Subtype"
KEY_PARENT = "/Parent"
KEY_T = "/T"
KEY_TU = "/TU"
KEY_V = "/V"
KEY_AS = "/AS"
KEY_RECT = "/Rect"
KEY_ANNOT_FLAGS = "/F"
SUBTYPE_WIDGET = "/Widget"
FT_TEXT = "/Tx"
FT_CHOICE = "/Ch"
OFF_STATE = "/Off"
NAME_SEPARATOR = "."
ANNOT_FLAG_HIDDEN = 1 << 1


class FormWidget(NamedTuple):
    page: int
    bbox: tuple[float, float, float, float]  # top-origin, like parse_bbox_layout
    name: str
    label: str | None
    value: str


def extract_acroform(pdf_bytes: bytes, document_uuid: UUID) -> FormExtraction:
    widgets = read_widgets(pdf_bytes)
    toggles = read_toggles(pdf_bytes)
    lines, unresolved = finish_form_lines(
        extract_source_lines(pdf_bytes, document_uuid), toggles, document_uuid
    )
    return FormExtraction(
        lines=lines,
        fields=[
            NewFormField(
                document_uuid=document_uuid,
                field_order=order,
                section=page_section(w.page),
                name=w.name,
                label=w.label,
                value=w.value,
                page=w.page,
            )
            for order, w in enumerate(widgets)
        ],
        toggles=len(toggles),
        checked=sum(1 for toggle in toggles if toggle.checked),
        unresolved=unresolved,
    )


def read_widgets(pdf_bytes: bytes) -> list[FormWidget]:
    """One entry per value-carrying field, at its first visible widget, in reading
    order. Empty text and choice fields are omitted."""
    seen: set[str] = set()
    widgets: list[FormWidget] = []
    for page_number, annot, height in _visible_widgets(pdf_bytes):
        field = _field_of(annot)
        name = _qualified_name(field)
        if name in seen:
            continue
        widget = _widget(field, annot, name, page_number, height)
        if widget is None:
            continue
        seen.add(name)
        widgets.append(widget)
    widgets.sort(key=lambda w: (w.page, w.bbox[1], w.bbox[0]))
    return widgets


def read_toggles(pdf_bytes: bytes) -> list[Toggle]:
    """One toggle per visible checkbox or radio widget, state from the widget's own
    appearance state (`/AS`), label from the field's tooltip."""
    toggles: list[Toggle] = []
    for page_number, annot, height in _visible_widgets(pdf_bytes):
        field = _field_of(annot)
        flags = int(_inherited(field, KEY_FF) or 0)
        if _inherited(field, KEY_FT) != FT_BUTTON or flags & FLAG_PUSHBUTTON:
            continue
        state = annot.get(KEY_AS)
        if state is None:
            state = _inherited(field, KEY_V)
        tool_tip = str(field.get(KEY_TU) or "").strip()
        toggles.append(
            Toggle(
                page=page_number,
                bbox=_rect_bbox(annot, height),
                checked=state is not None and str(state) != OFF_STATE,
                label=tool_tip or None,
            )
        )
    toggles.sort(key=lambda t: (t.page, t.bbox[1], t.bbox[0]))
    return toggles


def _visible_widgets(pdf_bytes: bytes) -> list[tuple[int, Any, float]]:
    """(page number, widget annotation, page height) of every visible widget."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    found: list[tuple[int, Any, float]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        height = float(page.mediabox.top)
        for ref in page.get(KEY_ANNOTS) or []:
            annot = ref.get_object()
            if annot.get(KEY_SUBTYPE) != SUBTYPE_WIDGET:
                continue
            if int(annot.get(KEY_ANNOT_FLAGS, 0)) & ANNOT_FLAG_HIDDEN:
                continue
            found.append((page_number, annot, height))
    return found


def _field_of(annot: Any) -> Any:
    field = annot if KEY_T in annot else annot.get(KEY_PARENT, annot)
    return field.get_object()


def _widget(
    field: Any, annot: Any, name: str, page: int, height: float
) -> FormWidget | None:
    field_type = _inherited(field, KEY_FT)
    flags = int(_inherited(field, KEY_FF) or 0)
    raw = _inherited(field, KEY_V)
    is_button = field_type == FT_BUTTON
    if field_type == FT_SIGNATURE or (is_button and flags & FLAG_PUSHBUTTON):
        return None
    if is_button:
        selected = raw is not None and str(raw) != OFF_STATE
        if flags & FLAG_RADIO:
            value = _name_value(raw) if selected else UNCHECKED
        else:
            value = CHECKED if selected else UNCHECKED
    elif field_type in (FT_TEXT, FT_CHOICE):
        value = _text_value(raw)
        if not value:
            return None
    else:
        return None
    tool_tip = str(field.get(KEY_TU) or "").strip()
    return FormWidget(
        page=page,
        bbox=_rect_bbox(annot, height),
        name=name,
        label=tool_tip or None,
        value=value,
    )


def _rect_bbox(annot: Any, height: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in annot[KEY_RECT])
    return (min(x0, x1), height - max(y0, y1), max(x0, x1), height - min(y0, y1))


def _qualified_name(field: Any) -> str:
    parts: list[str] = []
    node = field
    while node is not None:
        if KEY_T in node:
            parts.append(str(node[KEY_T]))
        parent = node.get(KEY_PARENT)
        node = parent.get_object() if parent is not None else None
    return NAME_SEPARATOR.join(reversed(parts))


def _inherited(field: Any, key: str) -> Any:
    node = field
    while node is not None:
        if key in node:
            return node[key]
        parent = node.get(KEY_PARENT)
        node = parent.get_object() if parent is not None else None
    return None


def _name_value(raw: Any) -> str:
    text = str(raw)
    return text[1:] if isinstance(raw, NameObject) else text


def _text_value(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, list):
        return ", ".join(str(v) for v in raw).strip()
    return str(raw).strip()
