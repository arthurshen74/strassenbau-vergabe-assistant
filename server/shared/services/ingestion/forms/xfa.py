"""XFA form extraction from the embedded XML packets.

A dynamic XFA form has no page content worth reading (the rendered page is Adobe's
"Please wait..." placeholder); the form lives in two packets: `template` (layout,
static text, field definitions) and `datasets` (the filled-in values). The template is
walked in document order; `<draw>` text becomes a line, a `<field>` becomes
`label: value` with the value looked up in datasets at the same subform path. Unnamed
subforms and areas are transparent to that path, as they are in XFA data binding.
Scripts are not evaluated, so a field hidden only by script is emitted anyway.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from uuid import UUID

from pypdf import PdfReader

from shared.models.form_field import NewFormField
from shared.models.source_line import NewSourceLine
from shared.services.ingestion.forms.detect import KEY_ACROFORM, KEY_ROOT, KEY_XFA
from shared.services.ingestion.forms.model import (
    CHECKED,
    UNCHECKED,
    FormExtraction,
    field_line,
    section_heading,
)

PACKET_TEMPLATE = "template"
PACKET_DATASETS = "datasets"

# Template element local names.
TAG_SUBFORM = "subform"
TAG_SUBFORM_SET = "subformSet"
TAG_AREA = "area"
TAG_PAGE_SET = "pageSet"
TAG_FIELD = "field"
TAG_DRAW = "draw"
TAG_EXCL_GROUP = "exclGroup"
TAG_UI = "ui"
TAG_VALUE = "value"
TAG_TEXT = "text"
TAG_EX_DATA = "exData"
TAG_ITEMS = "items"
TAG_CAPTION = "caption"
TAG_ASSIST = "assist"
TAG_TOOL_TIP = "toolTip"
TAG_BIND = "bind"
TAG_DATA = "data"
TAG_P = "p"
UI_CHECK_BUTTON = "checkButton"
UI_CHOICE_LIST = "choiceList"
SKIPPED_UIS = frozenset({"imageEdit", "button", "signature", "passwordEdit"})
ATTR_NAME = "name"
ATTR_PRESENCE = "presence"
ATTR_MATCH = "match"
HIDDEN_PRESENCES = frozenset({"hidden", "invisible", "inactive"})
BIND_NONE = "none"
TRANSPARENT_CONTAINERS = frozenset({TAG_SUBFORM_SET, TAG_AREA})

# A checkButton without <items> is on at "1".
DEFAULT_ON_VALUE = "1"
SKIPPED_NAME = re.compile(r"ID_|validate|Formularbutton")
XFA_PAGE = 1
NO_BBOX = (0.0, 0.0, 0.0, 0.0)
_WHITESPACE = re.compile(r"\s+")


def read_xfa_packets(pdf_bytes: bytes) -> dict[str, bytes]:
    """The `/XFA` array as {packet name: XML bytes}."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    xfa = reader.trailer[KEY_ROOT][KEY_ACROFORM][KEY_XFA]
    items = list(xfa)
    return {
        str(name): ref.get_object().get_data()
        for name, ref in zip(items[::2], items[1::2])
    }


def extract_xfa(pdf_bytes: bytes, document_uuid: UUID) -> FormExtraction:
    packets = read_xfa_packets(pdf_bytes)
    return extract_xfa_packets(
        packets[PACKET_TEMPLATE], packets.get(PACKET_DATASETS), document_uuid
    )


def extract_xfa_packets(
    template: bytes, datasets: bytes | None, document_uuid: UUID
) -> FormExtraction:
    """Walk the template in document order against the datasets values."""
    template_root = ET.fromstring(template)
    root_subform = _first_child(template_root, TAG_SUBFORM)
    data_root = _data_root(datasets, root_subform)
    walk = _XfaWalk(document_uuid, data_root)
    if root_subform is not None:
        walk.root(root_subform)
    return FormExtraction(lines=walk.lines, fields=walk.fields)


class _XfaWalk:
    """Accumulates lines and fields; headings are emitted lazily so an empty section
    leaves no heading behind."""

    def __init__(self, document_uuid: UUID, data_root: ET.Element | None) -> None:
        self.document_uuid = document_uuid
        self.data_root = data_root
        self.lines: list[NewSourceLine] = []
        self.fields: list[NewFormField] = []
        self.section = ""
        self.heading_pending = False

    def root(self, root_subform: ET.Element) -> None:
        """Master-page text (the Formblatt title) first, then every page subform. A
        top-level subform with no value-carrying field (the Adobe button bar) is not a
        page."""
        for child in root_subform:
            if _local(child) == TAG_PAGE_SET:
                for draw in child.iter():
                    if _local(draw) == TAG_DRAW and not _hidden(draw):
                        self._draw(draw)
        for child in root_subform:
            if (
                _local(child) == TAG_SUBFORM
                and not _hidden(child)
                and _has_value_field(child)
            ):
                self.page(child, [_name(child)] if _name(child) else [])

    def page(self, page: ET.Element, path: list[str]) -> None:
        self._open_section(_name(page) or "")
        for child in page:
            if _local(child) == TAG_SUBFORM and _name(child) and not _hidden(child):
                self._open_section(_name(child) or "")
                self.container(child, [*path, _name(child) or ""])
            else:
                self.node(child, path)

    def container(self, element: ET.Element, path: list[str]) -> None:
        for child in element:
            self.node(child, path)

    def node(self, element: ET.Element, path: list[str]) -> None:
        if _hidden(element):
            return
        tag = _local(element)
        if tag == TAG_SUBFORM:
            name = _name(element)
            self.container(element, [*path, name] if name else path)
        elif tag in TRANSPARENT_CONTAINERS:
            self.container(element, path)
        elif tag == TAG_DRAW:
            self._draw(element)
        elif tag == TAG_FIELD:
            self._field(element, path)
        elif tag == TAG_EXCL_GROUP:
            self._excl_group(element, path)

    def _draw(self, draw: ET.Element) -> None:
        for paragraph in _draw_paragraphs(draw):
            self._line(paragraph)

    def _field(self, field: ET.Element, path: list[str]) -> None:
        name = _name(field) or ""
        ui = _ui_kind(field)
        if ui in SKIPPED_UIS or SKIPPED_NAME.search(name):
            return
        raw = self._value(field, path)
        if ui == UI_CHECK_BUTTON:
            value = CHECKED if raw == _on_value(field) else UNCHECKED
        elif ui == UI_CHOICE_LIST:
            value = _choice_display(field, raw)
        else:
            value = raw
        if not value:
            return
        self._emit_field(name, _label(field), value)

    def _excl_group(self, group: ET.Element, path: list[str]) -> None:
        """A radio group: the value is the caption of the child whose on-value equals
        the group's datasets value. Nothing selected emits nothing."""
        name = _name(group) or ""
        raw = self._value(group, path)
        if not raw:
            return
        for option in group:
            if _local(option) == TAG_FIELD and _on_value(option) == raw:
                self._emit_field(name, _label(group), _label(option) or raw)
                return

    def _emit_field(self, name: str, label: str | None, value: str) -> None:
        self._line(field_line(label or name, _collapse(value)))
        self.fields.append(
            NewFormField(
                document_uuid=self.document_uuid,
                field_order=len(self.fields),
                section=self.section,
                name=name,
                label=label,
                value=value,
                page=XFA_PAGE,
            )
        )

    def _value(self, element: ET.Element, path: list[str]) -> str:
        """The datasets value at the element's binding path, else the template
        default."""
        bind = _first_child(element, TAG_BIND)
        name = _name(element)
        if name and (bind is None or bind.get(ATTR_MATCH) != BIND_NONE):
            data = _lookup(self.data_root, path, name)
            if data is not None:
                return data.strip()
        return _template_value(element)

    def _open_section(self, section: str) -> None:
        self.section = section
        self.heading_pending = bool(section)

    def _line(self, text: str) -> None:
        if not text:
            return
        if self.heading_pending:
            self.heading_pending = False
            self._append(section_heading(self.section))
        self._append(text)

    def _append(self, text: str) -> None:
        self.lines.append(
            NewSourceLine(
                document_uuid=self.document_uuid,
                line_id=len(self.lines),
                page=XFA_PAGE,
                bbox=NO_BBOX,
                line_text=text,
            )
        )


def _data_root(
    datasets: bytes | None, root_subform: ET.Element | None
) -> ET.Element | None:
    """The data node bound to the template's root subform: `xfa:data/<rootName>`."""
    if datasets is None or root_subform is None:
        return None
    data = _first_child(ET.fromstring(datasets), TAG_DATA)
    if data is None:
        return None
    return _first_child(data, _name(root_subform) or "")


def _lookup(data_root: ET.Element | None, path: list[str], name: str) -> str | None:
    """Text of `<path...>/<name>` under the data root; falls back to the first node of
    that name anywhere when the path does not resolve (global binding)."""
    if data_root is None:
        return None
    node: ET.Element | None = data_root
    for step in path:
        node = _first_child(node, step) if node is not None else None
    leaf = _first_child(node, name) if node is not None else None
    if leaf is None:
        leaf = next((e for e in data_root.iter() if _local(e) == name), None)
    if leaf is None or len(leaf):
        return None
    return leaf.text or ""


def _has_value_field(element: ET.Element) -> bool:
    return any(
        _local(e) in (TAG_FIELD, TAG_EXCL_GROUP) and _ui_kind(e) not in SKIPPED_UIS
        for e in element.iter()
    )


def _draw_paragraphs(draw: ET.Element) -> list[str]:
    """A draw's text: one entry per XHTML paragraph, or the plain text."""
    value = _first_child(draw, TAG_VALUE)
    if value is None:
        return []
    ex_data = _first_child(value, TAG_EX_DATA)
    if ex_data is not None:
        paragraphs = [e for e in ex_data.iter() if _local(e) == TAG_P]
        blocks = paragraphs or [ex_data]
        return [t for t in (_collapse("".join(b.itertext())) for b in blocks) if t]
    text = _first_child(value, TAG_TEXT)
    collapsed = _collapse(text.text or "") if text is not None else ""
    return [collapsed] if collapsed else []


def _label(element: ET.Element) -> str | None:
    """Caption text, else the tooltip, else None. A trailing colon is dropped, the
    line adds its own separator."""
    caption = _first_child(element, TAG_CAPTION)
    texts = _draw_paragraphs(caption) if caption is not None else []
    if not texts:
        assist = _first_child(element, TAG_ASSIST)
        tool_tip = _first_child(assist, TAG_TOOL_TIP) if assist is not None else None
        if tool_tip is not None and tool_tip.text:
            texts = [_collapse(tool_tip.text)]
    label = " ".join(texts).rstrip(":").strip()
    return label or None


def _template_value(element: ET.Element) -> str:
    value = _first_child(element, TAG_VALUE)
    if value is None or len(value) == 0:
        return ""
    return (value[0].text or "").strip()


def _on_value(field: ET.Element) -> str:
    items = _first_child(field, TAG_ITEMS)
    first = items[0] if items is not None and len(items) else None
    return (first.text or "").strip() if first is not None else DEFAULT_ON_VALUE


def _choice_display(field: ET.Element, raw: str) -> str:
    """Map a choice list's saved value to its display text when the field has a
    (display, save) pair of item lists."""
    item_lists = [c for c in field if _local(c) == TAG_ITEMS]
    if len(item_lists) != 2:
        return raw
    display = [(i.text or "").strip() for i in item_lists[0]]
    saved = [(i.text or "").strip() for i in item_lists[1]]
    return display[saved.index(raw)] if raw in saved else raw


def _ui_kind(field: ET.Element) -> str | None:
    ui = _first_child(field, TAG_UI)
    if ui is None or len(ui) == 0:
        return None
    return _local(ui[0])


def _hidden(element: ET.Element) -> bool:
    return element.get(ATTR_PRESENCE) in HIDDEN_PRESENCES


def _name(element: ET.Element) -> str | None:
    return element.get(ATTR_NAME)


def _first_child(element: ET.Element, local_name: str) -> ET.Element | None:
    return next((c for c in element if _local(c) == local_name), None)


def _local(element: ET.Element) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()
