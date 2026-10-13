"""Build small form PDFs with pypdf for the form tests: AcroForms with widgets, and
flattened pages drawn from a hand-built content stream (Helvetica base font, boxes as
four line segments or a rectangle, tick glyphs as text)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
FLAG_PUSHBUTTON = 1 << 16
FONT_NAME = "/F1"
TICK = "X"
TICK_SIZE = 8


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: str  # "/Tx", "/Btn"
    rect: tuple[float, float, float, float]  # PDF bottom-origin
    value: str | None = None  # text, or "/Yes" | "/Off" for a checkbox
    tool_tip: str | None = None
    flags: int = 0


@dataclass(frozen=True)
class Text:
    x: float
    y: float  # baseline, PDF bottom-origin
    text: str
    size: float = 10.0


@dataclass(frozen=True)
class Box:
    x: float
    y: float  # lower-left corner, PDF bottom-origin
    checked: bool = False
    side: float = 10.0
    style: Literal["lines", "rect"] = "lines"


def text_field(name: str, y: float, value: str, x: float = 50) -> FieldSpec:
    return FieldSpec(name, "/Tx", (x, y, x + 150, y + 15), value=value)


def acroform_pdf(
    fields: list[FieldSpec], *, xfa: bool = False, texts: list[Text] | None = None
) -> bytes:
    """A one-page PDF whose AcroForm holds `fields`, one widget each, with `texts`
    printed on the page. With `xfa`, an `/XFA` entry is added to the AcroForm."""
    writer = PdfWriter()
    _add_page(writer, _content(texts or [], []))
    refs = ArrayObject()
    for spec in fields:
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/T"): TextStringObject(spec.name),
                NameObject("/FT"): NameObject(spec.field_type),
                NameObject("/Rect"): ArrayObject(FloatObject(v) for v in spec.rect),
            }
        )
        if spec.flags:
            widget[NameObject("/Ff")] = NumberObject(spec.flags)
        if spec.tool_tip is not None:
            widget[NameObject("/TU")] = TextStringObject(spec.tool_tip)
        if spec.value is not None:
            widget[NameObject("/V")] = (
                NameObject(spec.value)
                if spec.value.startswith("/")
                else TextStringObject(spec.value)
            )
        refs.append(writer.add_annotation(0, widget).indirect_reference)
    acroform = DictionaryObject({NameObject("/Fields"): refs})
    if xfa:
        packet = DecodedStreamObject()
        packet.set_data(b"<template/>")
        acroform[NameObject("/XFA")] = ArrayObject(
            [TextStringObject("template"), writer._add_object(packet)]
        )
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acroform)
    return _bytes(writer)


def flattened_pdf(boxes: list[Box], texts: list[Text]) -> bytes:
    """A one-page PDF with no AcroForm: printed texts and drawn checkboxes, a tick
    glyph inside every checked box."""
    return flattened_pdf_pages([(boxes, texts)])


def flattened_pdf_pages(pages: list[tuple[list[Box], list[Text]]]) -> bytes:
    """A multi-page PDF with no AcroForm, one (boxes, texts) pair per page."""
    writer = PdfWriter()
    for boxes, texts in pages:
        _add_page(writer, _content(texts, boxes))
    return _bytes(writer)


def three_field_form() -> bytes:
    return acroform_pdf(
        [
            text_field("Vergabenummer", 700, "26/001"),
            text_field("Ort", 680, "Berlin"),
            text_field("Datum", 660, "15.10.2026"),
        ]
    )


HVA_111_FOOTER = "111 HVA B-StB Vorlage Aufforderung zur Angebotsabgabe 03-23"


def hva_111_page() -> bytes:
    """An excerpt of HVA B-StB 111 page 3 in its real geometry: number column at
    x=62, boxes at x=90 (nested at 104), labels 4.9pt right of the box."""
    texts = [
        Text(62, 800, HVA_111_FOOTER, 8),
        Text(62, 750, "4"),
        Text(90.7, 750, "Losweise Vergabe:"),
        Text(104.9, 722, "Nein"),
        Text(104.9, 707, "Ja, Angebotsabgabe ist zugelassen"),
        Text(119, 692, "nur für ein Los"),
        Text(104.9, 677, "Fortsetzung der Option"),
        Text(62, 650, "6"),
        Text(90.7, 650, "Nebenangebote"),
        Text(62, 630, "6.1"),
        Text(104.9, 630, "Nebenangebote sind nicht zugelassen"),
        Text(62, 615, "6.2"),
        Text(104.9, 615, "Nebenangebote sind zugelassen"),
        Text(62, 590, "7"),
        Text(90.7, 590, "Angebotswertung:"),
        Text(104.9, 572, "Preis"),
    ]
    boxes = [
        Box(90, 720, checked=True),
        Box(90, 705),
        Box(104, 690),
        Box(90, 628, checked=True, style="rect"),
        Box(90, 613),
        Box(90, 570),
    ]
    return flattened_pdf(boxes, texts)


def _content(texts: list[Text], boxes: list[Box]) -> bytes:
    ops: list[str] = []
    for box in boxes:
        x0, y0, x1, y1 = box.x, box.y, box.x + box.side, box.y + box.side
        if box.style == "rect":
            ops.append(f"{x0} {y0} {box.side} {box.side} re S")
        else:
            ops.append(f"{x0} {y0} m {x1} {y0} l S")
            ops.append(f"{x0} {y1} m {x1} {y1} l S")
            ops.append(f"{x0} {y0} m {x0} {y1} l S")
            ops.append(f"{x1} {y0} m {x1} {y1} l S")
        if box.checked:
            ops.append(_text_op(Text(x0 + 2.3, y0 + 2, TICK, TICK_SIZE)))
    ops.extend(_text_op(text) for text in texts)
    return "\n".join(ops).encode("cp1252")


def _text_op(text: Text) -> str:
    escaped = text.text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT {FONT_NAME} {text.size} Tf {text.x} {text.y} Td ({escaped}) Tj ET"


def _add_page(writer: PdfWriter, content: bytes) -> None:
    page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject(FONT_NAME): font})}
    )


def _bytes(writer: PdfWriter) -> bytes:
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
