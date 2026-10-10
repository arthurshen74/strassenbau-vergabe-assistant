"""Build small fillable-form PDFs with pypdf for the form tests."""

from __future__ import annotations

import io
from dataclasses import dataclass

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


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: str  # "/Tx", "/Btn"
    rect: tuple[float, float, float, float]  # PDF bottom-origin
    value: str | None = None  # text, or "/Yes" | "/Off" for a checkbox
    tool_tip: str | None = None
    flags: int = 0


def text_field(name: str, y: float, value: str, x: float = 50) -> FieldSpec:
    return FieldSpec(name, "/Tx", (x, y, x + 150, y + 15), value=value)


def acroform_pdf(fields: list[FieldSpec], *, xfa: bool = False) -> bytes:
    """A one-page PDF whose AcroForm holds `fields`, one widget each. With `xfa`, an
    `/XFA` entry is added to the AcroForm dictionary."""
    writer = PdfWriter()
    writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
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
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def three_field_form() -> bytes:
    return acroform_pdf(
        [
            text_field("Vergabenummer", 700, "26/001"),
            text_field("Ort", 680, "Berlin"),
            text_field("Datum", 660, "15.10.2026"),
        ]
    )
