"""Toggle attachment shared by the geometric form readers (AcroForm, flattened).

The readers only locate toggles: a square on a page and whether it is ticked. What the
option says is printed next to the square, so the state is attached to the pdftotext
line to the right of it, and the result is the same line contract for both kinds.
Before that, repeated page furniture is removed (`forms/furniture.py`) and `pdftotext
-bbox-layout` artefacts are repaired: a tick glyph or a section number that the layout
emitted as a block of its own is re-attached to the line it sits in front of. Numbered
headings then open the form sections, lines are put in reading order (page, y, x) and
renumbered. Pure functions over `NewSourceLine`; `bbox` is the only geometry used.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple
from uuid import UUID

from shared.models.form_field import NewFormField
from shared.models.source_line import NewSourceLine
from shared.services.ingestion.forms.furniture import remove_furniture
from shared.services.ingestion.forms.model import (
    CHECKED,
    FORM_SECTION_PREFIX,
    OPTION_CHECKED_PREFIX,
    UNCHECKED,
    Toggle,
    is_option_line,
    option_label,
    option_line,
    section_heading,
)

TOGGLE_Y_TOLERANCE = 4.0
# HVA prints the Anlagen labels 18.7pt right of their box; the option labels 4.8pt.
TOGGLE_X_GAP = 20.0
TICK_GLYPHS = frozenset("xX×✓✔✗✘☑☒")
_TICK_CLASS = "[" + "".join(sorted(TICK_GLYPHS)) + "]"
MARGINAL_TOKEN = re.compile(rf"^(?:{_TICK_CLASS}|\d+(?:\.\d+)*)$")
LEADING_TICK = re.compile(rf"^{_TICK_CLASS}\s+")
# A section heading: a one- or two-digit number without a dot, then text, at the page's
# left margin. Footers (`111 HVA B-StB ...`) and postcodes have more digits, `6.1` is a
# content line, and `11 VOB/B ...` after a line break at `§` sits in the text column.
HEADING = re.compile(r"^\d{1,2}\s+\S")
HEADING_MARGIN_TOLERANCE = 1.0
SECTION_PAGE = "Seite {page}"
TOGGLE_FIELD_NAME = "p{page}-{index}"
NO_BBOX = (0.0, 0.0, 0.0, 0.0)


def page_section(page: int) -> str:
    return SECTION_PAGE.format(page=page)


class FinishedLines(NamedTuple):
    lines: list[NewSourceLine]
    unresolved: int
    furniture: int


def finish_form_lines(
    lines: list[NewSourceLine], toggles: list[Toggle], document_uuid: UUID
) -> FinishedLines:
    """The shared tail of the geometric readers: drop repeated page furniture, repair
    marginal tokens, attach the toggles, open the sections."""
    content, furniture = remove_furniture(lines)
    merged = merge_marginal_tokens(content)
    attached, unresolved = attach_toggles(merged, toggles, document_uuid)
    return FinishedLines(
        insert_headings(attached, document_uuid), unresolved, furniture
    )


def merge_marginal_tokens(lines: list[NewSourceLine]) -> list[NewSourceLine]:
    """A line that is only a tick glyph or a section number is merged into the nearest
    line of the same row to its right: the number is prefixed, the glyph dropped (its
    state comes from the toggle), and the line's bbox grows to the token's x0 so the
    number column governs nesting. A token without a partner is kept as is."""
    is_token = [MARGINAL_TOKEN.match(line.line_text) is not None for line in lines]
    prefixes: dict[int, list[tuple[float, str]]] = {}
    extended: dict[int, float] = {}
    consumed: set[int] = set()
    for index, line in enumerate(lines):
        if not is_token[index]:
            continue
        partner = _token_partner(lines, is_token, line)
        if partner is None:
            continue
        consumed.add(index)
        extended[partner] = min(extended.get(partner, line.bbox[0]), line.bbox[0])
        if line.line_text not in TICK_GLYPHS:
            prefixes.setdefault(partner, []).append((line.bbox[0], line.line_text))
    result: list[NewSourceLine] = []
    for index, line in enumerate(lines):
        if index in consumed:
            continue
        if index in extended:
            numbers = [text for _, text in sorted(prefixes.get(index, []))]
            x0 = min(extended[index], line.bbox[0])
            line = line.model_copy(
                update={
                    "line_text": " ".join([*numbers, line.line_text]),
                    "bbox": (x0, line.bbox[1], line.bbox[2], line.bbox[3]),
                }
            )
        result.append(line)
    return result


def attach_toggles(
    lines: list[NewSourceLine], toggles: list[Toggle], document_uuid: UUID
) -> tuple[list[NewSourceLine], int]:
    """Prefix each toggle's state onto the printed line to its right: the line of the
    same row that starts within TOGGLE_X_GAP of the square's right edge, or starts
    further left (a merged glyph or section number) and runs past it. A toggle without
    a printed line but with a label emits `[x] label` at its own position; one with
    neither is counted as unresolved. Lines come back in (page, y, x) order with
    renumbered ids."""
    marked: dict[int, bool] = {}
    fallback: list[NewSourceLine] = []
    unresolved = 0
    for toggle in toggles:
        partner = _toggle_partner(lines, marked, toggle)
        if partner is not None:
            marked[partner] = toggle.checked
        elif toggle.label:
            fallback.append(
                NewSourceLine(
                    document_uuid=document_uuid,
                    line_id=0,
                    page=toggle.page,
                    bbox=toggle.bbox,
                    line_text=option_line(toggle.label, toggle.checked),
                )
            )
        else:
            unresolved += 1
    result = [
        line
        if index not in marked
        else line.model_copy(
            update={
                "line_text": option_line(
                    LEADING_TICK.sub("", line.line_text), marked[index]
                )
            }
        )
        for index, line in enumerate(lines)
    ]
    return _renumber(result + fallback), unresolved


def insert_headings(
    lines: list[NewSourceLine], document_uuid: UUID
) -> list[NewSourceLine]:
    """A numbered heading line becomes a `## ` section line; a page without one opens
    with `## Seite n`. Lines are expected in reading order."""
    margins = _page_margins(lines)
    headings = {index for index, line in enumerate(lines) if _is_heading(line, margins)}
    headed_pages = {lines[index].page for index in headings}
    result: list[NewSourceLine] = []
    current_page = 0
    for index, line in enumerate(lines):
        if line.page != current_page:
            current_page = line.page
            if current_page not in headed_pages:
                result.append(
                    NewSourceLine(
                        document_uuid=document_uuid,
                        line_id=0,
                        page=current_page,
                        bbox=NO_BBOX,
                        line_text=section_heading(page_section(current_page)),
                    )
                )
        if index in headings:
            line = line.model_copy(
                update={"line_text": section_heading(line.line_text)}
            )
        result.append(line)
    return _renumber(result, sort=False)


def option_fields(
    lines: list[NewSourceLine], document_uuid: UUID
) -> list[NewFormField]:
    """One `form_fields` row per option line, under the section it sits in, named by
    page and running index."""
    fields: list[NewFormField] = []
    section = ""
    index_on_page: dict[int, int] = {}
    for line in lines:
        if line.line_text.startswith(FORM_SECTION_PREFIX):
            section = line.line_text[len(FORM_SECTION_PREFIX) :]
            continue
        if not is_option_line(line.line_text):
            continue
        index = index_on_page.get(line.page, 0)
        index_on_page[line.page] = index + 1
        checked = line.line_text.startswith(OPTION_CHECKED_PREFIX)
        fields.append(
            NewFormField(
                document_uuid=document_uuid,
                field_order=len(fields),
                section=section,
                name=TOGGLE_FIELD_NAME.format(page=line.page, index=index),
                label=option_label(line.line_text),
                value=CHECKED if checked else UNCHECKED,
                page=line.page,
            )
        )
    return fields


def _page_margins(lines: list[NewSourceLine]) -> dict[int, float]:
    """Leftmost x0 of the unmarked lines per page: the number column of a form."""
    margins: dict[int, float] = {}
    for line in lines:
        if not is_option_line(line.line_text):
            margins[line.page] = min(margins.get(line.page, line.bbox[0]), line.bbox[0])
    return margins


def _is_heading(line: NewSourceLine, margins: dict[int, float]) -> bool:
    return (
        HEADING.match(line.line_text) is not None
        and not is_option_line(line.line_text)
        and line.bbox[0] <= margins[line.page] + HEADING_MARGIN_TOLERANCE
    )


def _token_partner(
    lines: list[NewSourceLine], is_token: list[bool], token: NewSourceLine
) -> int | None:
    """The non-token line of the token's row to its right, nearest by yMin."""

    def accept(index: int, line: NewSourceLine) -> bool:
        return (
            not is_token[index]
            and line.page == token.page
            and abs(line.bbox[1] - token.bbox[1]) <= TOGGLE_Y_TOLERANCE
            and line.bbox[0] > token.bbox[0]
        )

    return _nearest(lines, accept, lambda line: abs(line.bbox[1] - token.bbox[1]))


def _toggle_partner(
    lines: list[NewSourceLine], marked: dict[int, bool], toggle: Toggle
) -> int | None:
    """The unmarked line of the toggle's row that starts within TOGGLE_X_GAP of the
    square's right edge or runs past it, nearest by vertical centre."""
    centre = _centre_y(toggle.bbox)

    def accept(index: int, line: NewSourceLine) -> bool:
        return (
            index not in marked
            and line.page == toggle.page
            and abs(_centre_y(line.bbox) - centre) <= TOGGLE_Y_TOLERANCE
            and line.bbox[0] <= toggle.bbox[2] + TOGGLE_X_GAP
            and line.bbox[2] > toggle.bbox[2]
        )

    return _nearest(lines, accept, lambda line: abs(_centre_y(line.bbox) - centre))


def _nearest(
    lines: list[NewSourceLine],
    accept: Callable[[int, NewSourceLine], bool],
    distance: Callable[[NewSourceLine], float],
) -> int | None:
    """Index of the accepted line with the smallest distance, leftmost on a tie."""
    candidates = [i for i, line in enumerate(lines) if accept(i, line)]
    if not candidates:
        return None
    return min(candidates, key=lambda i: (distance(lines[i]), lines[i].bbox[0]))


def _centre_y(bbox: tuple[float, float, float, float]) -> float:
    return (bbox[1] + bbox[3]) / 2


def _renumber(lines: list[NewSourceLine], *, sort: bool = True) -> list[NewSourceLine]:
    ordered = (
        sorted(lines, key=lambda line: (line.page, line.bbox[1], line.bbox[0]))
        if sort
        else lines
    )
    return [
        line.model_copy(update={"line_id": line_id})
        for line_id, line in enumerate(ordered)
    ]
