"""Render the SourceLine rows of an LV document as the line-numbered text the LLM reads.

Each kept line is prefixed with its `line_id` so the model can segment by reference without
reproducing text. Repeating page furniture (project header, filename/page footer, the title
and column-header band) is stripped from the rendering only -- the SourceLine rows stay
complete, so spans the model returns still index straight back into the full set (LV_PARSE.md
step 2)."""

from __future__ import annotations

from collections import defaultdict

from shared.models.source_line import SourceLine

LINE_ID_SEP = "\t"

# Furniture anchors: lines whose text starts with these prefixes, or equals these exactly,
# are page furniture regardless of how often they repeat (the footer's page number varies).
ANCHOR_PREFIXES = ("Projektnummer:", "Projektbezeichnung:", "Dateiname:")
ANCHOR_EXACT = ("LEISTUNGSVERZEICHNIS",)

# A line whose verbatim text appears on at least this many distinct pages is treated as
# repeating furniture (e.g. the column-header band).
FURNITURE_MIN_PAGES = 3


def render_line_numbered(source_lines: list[SourceLine]) -> tuple[str, list[int]]:
    """Return the line-numbered rendering and the list of line_ids it kept (furniture removed)."""
    ordered = sorted(source_lines, key=lambda line: line.line_id)
    furniture = _furniture_line_ids(ordered)
    kept = [line for line in ordered if line.line_id not in furniture]
    rendered = "\n".join(f"{line.line_id}{LINE_ID_SEP}{line.line_text}" for line in kept)
    return rendered, [line.line_id for line in kept]


def _furniture_line_ids(ordered: list[SourceLine]) -> set[int]:
    pages_by_text: dict[str, set[int]] = defaultdict(set)
    for line in ordered:
        pages_by_text[line.line_text].add(line.page)

    furniture: set[int] = set()
    for line in ordered:
        text = line.line_text.strip()
        is_anchor = text.startswith(ANCHOR_PREFIXES) or text in ANCHOR_EXACT
        repeats = len(pages_by_text[line.line_text]) >= FURNITURE_MIN_PAGES
        if is_anchor or repeats:
            furniture.add(line.line_id)
    return furniture
