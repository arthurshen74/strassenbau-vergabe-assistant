"""Flattened Formblatt extraction: page text plus the drawn checkboxes.

A flattened form has no fields; a checkbox is a small square drawn as four vector line
segments (or a rectangle), and a tick is a text glyph (`X`, `×`) placed inside it.
pdfplumber locates the squares and the glyphs in the same top-origin frame that
`pdftotext -bbox-layout` uses for the lines, so a toggle attaches by geometry alone.
A filled text field of a flattened form is plain printed text and stays a prose line;
`form_fields` rows are written for the toggles only.
"""

from __future__ import annotations

import io
from typing import Any
from uuid import UUID

import pdfplumber

from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.forms.model import FormExtraction, Toggle
from shared.services.ingestion.forms.toggles import (
    TICK_GLYPHS,
    finish_form_lines,
    option_fields,
)

BOX_MIN_SIDE = 6.0
BOX_MAX_SIDE = 12.0
# Two segments belong to one square when their ends agree within this distance.
EDGE_TOLERANCE = 1.0
GLYPH_SLACK = 1.0
BOX_GLYPHS = frozenset("☐❏❐❑❒")

# pdfplumber object keys (top-origin frame).
KEY_X0 = "x0"
KEY_X1 = "x1"
KEY_TOP = "top"
KEY_BOTTOM = "bottom"
KEY_TEXT = "text"

Bbox = tuple[float, float, float, float]


def extract_flattened(pdf_bytes: bytes, document_uuid: UUID) -> FormExtraction:
    toggles = find_boxes(pdf_bytes)
    lines, unresolved = finish_form_lines(
        extract_source_lines(pdf_bytes, document_uuid), toggles, document_uuid
    )
    return FormExtraction(
        lines=lines,
        fields=option_fields(lines, document_uuid),
        toggles=len(toggles),
        checked=sum(1 for toggle in toggles if toggle.checked),
        unresolved=unresolved,
    )


def find_boxes(pdf_bytes: bytes) -> list[Toggle]:
    """Every checkbox square of the document with its state, in (page, y, x) order.
    Checked iff a tick glyph has its centre inside the square."""
    toggles: list[Toggle] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            ticks = [c for c in page.chars if c[KEY_TEXT] in TICK_GLYPHS]
            squares = _dedupe(
                [
                    *_rect_squares(page.rects),
                    *_line_squares(page.lines),
                    *_glyph_squares(page.chars),
                ]
            )
            toggles.extend(
                Toggle(
                    page=page_number,
                    bbox=square,
                    checked=any(_centre_inside(c, square) for c in ticks),
                )
                for square in squares
            )
    toggles.sort(key=lambda t: (t.page, t.bbox[1], t.bbox[0]))
    return toggles


def _rect_squares(rects: list[dict[str, Any]]) -> list[Bbox]:
    return [_bbox(r) for r in rects if _is_square(_bbox(r))]


def _line_squares(lines: list[dict[str, Any]]) -> list[Bbox]:
    """Squares assembled from a pair of horizontal segments with the same ends and a
    vertical segment on one side spanning them."""
    horizontals: dict[tuple[float, float], list[float]] = {}
    verticals: list[Bbox] = []
    for line in lines:
        x0, top, x1, bottom = _bbox(line)
        if bottom - top <= EDGE_TOLERANCE and BOX_MIN_SIDE <= x1 - x0 <= BOX_MAX_SIDE:
            horizontals.setdefault((round(x0), round(x1)), []).append(top)
        elif x1 - x0 <= EDGE_TOLERANCE:
            verticals.append((x0, top, x1, bottom))
    squares: list[Bbox] = []
    for (x0, x1), tops in horizontals.items():
        ordered = sorted(tops)
        index = 0
        while index + 1 < len(ordered):
            top, bottom = ordered[index], ordered[index + 1]
            square = (float(x0), top, float(x1), bottom)
            if _is_square(square) and _has_side(square, verticals):
                squares.append(square)
                index += 2
            else:
                index += 1
    return squares


def _glyph_squares(chars: list[dict[str, Any]]) -> list[Bbox]:
    """Box characters of a symbol font count as a square without vector lines."""
    return [_bbox(c) for c in chars if c[KEY_TEXT] in BOX_GLYPHS]


def _has_side(square: Bbox, verticals: list[Bbox]) -> bool:
    x0, top, x1, bottom = square
    return any(
        (abs(v[0] - x0) <= EDGE_TOLERANCE or abs(v[0] - x1) <= EDGE_TOLERANCE)
        and v[1] <= top + EDGE_TOLERANCE
        and v[3] >= bottom - EDGE_TOLERANCE
        for v in verticals
    )


def _is_square(bbox: Bbox) -> bool:
    return all(
        BOX_MIN_SIDE <= side <= BOX_MAX_SIDE
        for side in (bbox[2] - bbox[0], bbox[3] - bbox[1])
    )


def _centre_inside(char: dict[str, Any], square: Bbox) -> bool:
    x0, top, x1, bottom = _bbox(char)
    cx, cy = (x0 + x1) / 2, (top + bottom) / 2
    return (
        square[0] - GLYPH_SLACK <= cx <= square[2] + GLYPH_SLACK
        and square[1] - GLYPH_SLACK <= cy <= square[3] + GLYPH_SLACK
    )


def _dedupe(squares: list[Bbox]) -> list[Bbox]:
    seen: set[tuple[int, int]] = set()
    unique: list[Bbox] = []
    for square in squares:
        key = (round(square[0]), round(square[1]))
        if key not in seen:
            seen.add(key)
            unique.append(square)
    return unique


def _bbox(obj: dict[str, Any]) -> Bbox:
    return (
        float(obj[KEY_X0]),
        float(obj[KEY_TOP]),
        float(obj[KEY_X1]),
        float(obj[KEY_BOTTOM]),
    )
