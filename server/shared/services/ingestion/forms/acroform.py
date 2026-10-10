"""AcroForm extraction: poppler page text plus what it cannot see.

`pdftotext -bbox-layout` renders static text and text-field appearances with geometry,
so it stays the source of the page lines. It does not render checkbox or radio state in
a usable form; for every such field with a `/TU` label, one `label: ja|nein` line is
appended after its page's lines. The structured fields come from the widget annotations
in reading order (page, top to bottom, left to right).
"""

from __future__ import annotations

import io
from typing import Any, NamedTuple
from uuid import UUID

from pypdf import PdfReader
from pypdf.generic import NameObject

from shared.models.form_field import NewFormField
from shared.models.source_line import NewSourceLine
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
    field_line,
    section_heading,
)

KEY_ANNOTS = "/Annots"
KEY_SUBTYPE = "/Subtype"
KEY_PARENT = "/Parent"
KEY_T = "/T"
KEY_TU = "/TU"
KEY_V = "/V"
KEY_RECT = "/Rect"
KEY_ANNOT_FLAGS = "/F"
SUBTYPE_WIDGET = "/Widget"
FT_TEXT = "/Tx"
FT_CHOICE = "/Ch"
OFF_STATE = "/Off"
NAME_SEPARATOR = "."
ANNOT_FLAG_HIDDEN = 1 << 1
SECTION_PAGE = "Seite {page}"
NO_BBOX = (0.0, 0.0, 0.0, 0.0)


class FormWidget(NamedTuple):
    page: int
    bbox: tuple[float, float, float, float]  # top-origin, like parse_bbox_layout
    name: str
    label: str | None
    value: str
    is_toggle: bool  # checkbox or radio


def page_section(page: int) -> str:
    return SECTION_PAGE.format(page=page)


def extract_acroform(pdf_bytes: bytes, document_uuid: UUID) -> FormExtraction:
    widgets = read_widgets(pdf_bytes)
    page_lines = extract_source_lines(pdf_bytes, document_uuid)
    return FormExtraction(
        lines=_merge_lines(page_lines, widgets, document_uuid),
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
    )


def read_widgets(pdf_bytes: bytes) -> list[FormWidget]:
    """One entry per value-carrying field, at its first visible widget, in reading
    order. Empty text and choice fields are omitted."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    seen: set[str] = set()
    widgets: list[FormWidget] = []
    for page_number, page in enumerate(reader.pages, start=1):
        height = float(page.mediabox.top)
        for ref in page.get(KEY_ANNOTS) or []:
            annot = ref.get_object()
            if annot.get(KEY_SUBTYPE) != SUBTYPE_WIDGET:
                continue
            if int(annot.get(KEY_ANNOT_FLAGS, 0)) & ANNOT_FLAG_HIDDEN:
                continue
            field = annot if KEY_T in annot else annot.get(KEY_PARENT, annot)
            field = field.get_object()
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


def _widget(
    field: Any, annot: Any, name: str, page: int, height: float
) -> FormWidget | None:
    field_type = _inherited(field, KEY_FT)
    flags = int(_inherited(field, KEY_FF) or 0)
    raw = _inherited(field, KEY_V)
    is_toggle = field_type == FT_BUTTON
    if field_type == FT_SIGNATURE or (is_toggle and flags & FLAG_PUSHBUTTON):
        return None
    if is_toggle:
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
    x0, y0, x1, y1 = (float(v) for v in annot[KEY_RECT])
    tool_tip = str(field.get(KEY_TU) or "").strip()
    return FormWidget(
        page=page,
        bbox=(min(x0, x1), height - max(y0, y1), max(x0, x1), height - min(y0, y1)),
        name=name,
        label=tool_tip or None,
        value=value,
        is_toggle=is_toggle,
    )


def _merge_lines(
    page_lines: list[NewSourceLine], widgets: list[FormWidget], document_uuid: UUID
) -> list[NewSourceLine]:
    """Per page: a `## Seite n` heading, the page's pdftotext lines, then its labelled
    checkbox/radio lines. line_id is renumbered across the result."""
    pages = sorted(
        {line.page for line in page_lines}
        | {w.page for w in widgets if w.is_toggle and w.label}
    )
    merged: list[tuple[int, tuple[float, float, float, float], str]] = []
    for page in pages:
        merged.append((page, NO_BBOX, section_heading(page_section(page))))
        merged.extend(
            (line.page, line.bbox, line.line_text)
            for line in page_lines
            if line.page == page
        )
        merged.extend(
            (w.page, w.bbox, field_line(w.label, w.value))
            for w in widgets
            if w.page == page and w.is_toggle and w.label
        )
    return [
        NewSourceLine(
            document_uuid=document_uuid,
            line_id=line_id,
            page=page,
            bbox=bbox,
            line_text=text,
        )
        for line_id, (page, bbox, text) in enumerate(merged)
    ]


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
