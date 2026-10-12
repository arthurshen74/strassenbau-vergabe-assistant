"""Pre-filled box states as a labeling aid; not the detector under test.

Squares come from pdfplumber (`rects` of 6-12pt, squares assembled from horizontal
line pairs) and, on AcroForms, from checkbox widgets whose `/AS` gives the state. A
vector square is checked when a tick glyph sits inside it. Each square is attached to
the nearest extracted line to the right whose top is within 4pt; marginal-token lines
(the glyph or a section number) are never attached.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from scripts.form_labeler.store import LineState
from shared.models.source_line import NewSourceLine

BOX_MIN_SIDE = 6.0
BOX_MAX_SIDE = 12.0
EDGE_TOLERANCE = 1.5
LEFT_SLACK = 6.0
CENTRE_TOLERANCE = 5.0
DIAGONAL_MIN = 2.0
GLYPH_SLACK = 1.0
Y_TOLERANCE = 4.0
X_GAP = 90.0
TICK_GLYPHS = frozenset("xX×✓✔")
TICK_FONTS = ("ZapfDingbats", "Wingdings")
MARGINAL_TOKEN = re.compile(r"^(?:[xX×✓✔]|\d+(?:\.\d+)*|\d+\))$")

KEY_ANNOTS = "/Annots"
KEY_SUBTYPE = "/Subtype"
KEY_PARENT = "/Parent"
KEY_FT = "/FT"
KEY_FF = "/Ff"
KEY_AS = "/AS"
KEY_RECT = "/Rect"
SUBTYPE_WIDGET = "/Widget"
FT_BUTTON = "/Btn"
AS_OFF = "/Off"
FLAG_PUSHBUTTON = 1 << 16

Box = tuple[float, float, float, float]  # x0, top, x1, bottom (top-origin)


def propose(
    pdf_path: Path, page: int, lines: list[NewSourceLine]
) -> dict[int, LineState]:
    """Proposed state per index into `lines` for every square that attaches to a
    line."""
    pdf_bytes = pdf_path.read_bytes()
    squares = dict(_widget_squares(pdf_bytes, page))
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        plumber_page = pdf.pages[page - 1]
        for square in _vector_squares(plumber_page):
            squares.setdefault(
                square,
                _has_tick(plumber_page, square) or _has_diagonal(plumber_page, square),
            )
    proposals: dict[int, LineState] = {}
    for square, checked in squares.items():
        index = _attach(square, lines)
        if index is not None and index not in proposals:
            proposals[index] = LineState.CHECKED if checked else LineState.UNCHECKED
    return proposals


def _vector_squares(page: pdfplumber.page.Page) -> list[Box]:
    squares = [
        _rounded((r["x0"], r["top"], r["x1"], r["bottom"]))
        for r in page.rects
        if _is_box_side(r["width"]) and _is_box_side(r["height"])
    ]
    horizontals = sorted(
        (h for h in page.lines if h["height"] < EDGE_TOLERANCE), key=lambda h: h["top"]
    )
    for i, top in enumerate(horizontals):
        if not _is_box_side(top["x1"] - top["x0"]):
            continue
        for bottom in horizontals[i + 1 :]:
            gap = bottom["top"] - top["top"]
            if gap > BOX_MAX_SIDE:
                break
            if (
                _is_box_side(gap)
                and abs(bottom["x0"] - top["x0"]) <= EDGE_TOLERANCE
                and abs(bottom["x1"] - top["x1"]) <= EDGE_TOLERANCE
            ):
                squares.append(
                    _rounded((top["x0"], top["top"], top["x1"], bottom["top"]))
                )
                break
    return squares


def _widget_squares(pdf_bytes: bytes, page: int) -> list[tuple[Box, bool]]:
    """Checkbox and radio widgets of an AcroForm page with their `/AS` state."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pdf_page = reader.pages[page - 1]
    height = float(pdf_page.mediabox.height)
    squares: list[tuple[Box, bool]] = []
    for ref in pdf_page.get(KEY_ANNOTS) or []:
        annot = ref.get_object()
        if (
            annot.get(KEY_SUBTYPE) != SUBTYPE_WIDGET
            or _inherited(annot, KEY_FT) != FT_BUTTON
            or int(_inherited(annot, KEY_FF) or 0) & FLAG_PUSHBUTTON
        ):
            continue
        x0, y0, x1, y1 = (float(v) for v in annot[KEY_RECT])
        state = annot.get(KEY_AS)
        squares.append(
            (_rounded((x0, height - y1, x1, height - y0)), state not in (None, AS_OFF))
        )
    return squares


def _inherited(annot, key: str):  # type: ignore[no-untyped-def]
    """A field attribute, looked up through the widget's parent chain."""
    node = annot
    while node is not None:
        if key in node:
            return node[key]
        parent = node.get(KEY_PARENT)
        node = parent.get_object() if parent is not None else None
    return None


def _has_tick(page: pdfplumber.page.Page, square: Box) -> bool:
    x0, top, x1, bottom = square
    for char in page.chars:
        if char["text"] not in TICK_GLYPHS and not any(
            font in char["fontname"] for font in TICK_FONTS
        ):
            continue
        cx = (char["x0"] + char["x1"]) / 2
        cy = (char["top"] + char["bottom"]) / 2
        if (
            x0 - GLYPH_SLACK <= cx <= x1 + GLYPH_SLACK
            and top - GLYPH_SLACK <= cy <= bottom + GLYPH_SLACK
        ):
            return True
    return False


def _has_diagonal(page: pdfplumber.page.Page, square: Box) -> bool:
    """A tick drawn as strokes: a non-axis-aligned line inside the square."""
    x0, top, x1, bottom = square
    for line in page.lines:
        if line["width"] < DIAGONAL_MIN or line["height"] < DIAGONAL_MIN:
            continue
        if (
            line["x0"] >= x0 - GLYPH_SLACK
            and line["x1"] <= x1 + GLYPH_SLACK
            and line["top"] >= top - GLYPH_SLACK
            and line["bottom"] <= bottom + GLYPH_SLACK
        ):
            return True
    return False


def _attach(square: Box, lines: list[NewSourceLine]) -> int | None:
    """Nearest line level with the square whose x0 is inside or up to X_GAP right of
    it. A line merged with the tick glyph may start LEFT_SLACK left of the square. A
    marginal token in between (a number column, the glyph itself) is hopped over and
    extends the reach from its right edge."""
    x0, top, x1, bottom = square
    centre = (top + bottom) / 2
    level = sorted(
        (
            (index, line)
            for index, line in enumerate(lines)
            if abs(line.bbox[1] - top) <= Y_TOLERANCE
            or abs((line.bbox[1] + line.bbox[3]) / 2 - centre) <= CENTRE_TOLERANCE
        ),
        key=lambda item: item[1].bbox[0],
    )
    reach = x1 + X_GAP
    for index, line in level:
        lx0 = line.bbox[0]
        if lx0 < x0 - LEFT_SLACK:
            continue
        if lx0 > reach:
            return None
        if MARGINAL_TOKEN.match(line.line_text):
            reach = max(reach, line.bbox[2] + X_GAP)
            continue
        return index
    return None


def _is_box_side(length: float) -> bool:
    return BOX_MIN_SIDE <= length <= BOX_MAX_SIDE


def _rounded(box: tuple[float, float, float, float]) -> Box:
    return tuple(round(v, 1) for v in box)  # type: ignore[return-value]
