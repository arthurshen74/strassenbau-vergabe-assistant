"""Page furniture detection for form pages: headers and footers by repetition.

A line that recurs on most pages of a document at the same height is page furniture
(`111 HVA B-StB ... 03-23`, `Seite 3`, a repeated Kopf block), whatever the form
family. It is found by structure alone: the text with digit runs collapsed, clustered
by vertical position, counted over distinct pages. The first occurrence stays, so a
title repeated on every page of a two-page form is still read once; the repeats never
reach a chunk and never clear the nesting of an unchecked option at a page break. Tick
glyphs and bare section numbers are too short to count. Pure functions over
`NewSourceLine`; a single-page document has no furniture by construction.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from shared.models.source_line import NewSourceLine

# A line is furniture when its key recurs on at least FURNITURE_MIN_PAGES pages and on
# at least FURNITURE_PAGE_SHARE of the document's pages, within FURNITURE_Y_TOLERANCE.
FURNITURE_MIN_PAGES = 2
FURNITURE_PAGE_SHARE = 0.5
FURNITURE_Y_TOLERANCE = 6.0
FURNITURE_MIN_KEY_CHARS = 3
DIGITS = re.compile(r"\d+")
DIGIT_PLACEHOLDER = "#"
_WHITESPACE = re.compile(r"\s+")


def remove_furniture(
    lines: list[NewSourceLine],
) -> tuple[list[NewSourceLine], int]:
    """The lines without repeated page furniture, and how many were removed."""
    furniture = find_furniture(lines)
    kept = [line for index, line in enumerate(lines) if index not in furniture]
    return kept, len(furniture)


def find_furniture(lines: list[NewSourceLine]) -> set[int]:
    """Indices of the furniture repeats: every occurrence of a recurring line but
    its first in reading order."""
    pages = {line.page for line in lines}
    needed = max(FURNITURE_MIN_PAGES, math.ceil(len(pages) * FURNITURE_PAGE_SHARE))
    if len(pages) < FURNITURE_MIN_PAGES:
        return set()
    by_key: dict[str, list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        key = furniture_key(line.line_text)
        if len(key) >= FURNITURE_MIN_KEY_CHARS:
            by_key[key].append(index)
    furniture: set[int] = set()
    for indices in by_key.values():
        for cluster in _y_clusters(lines, indices):
            if len({lines[i].page for i in cluster}) < needed:
                continue
            first = min(
                cluster,
                key=lambda i: (lines[i].page, lines[i].bbox[1], lines[i].bbox[0]),
            )
            furniture.update(i for i in cluster if i != first)
    return furniture


def furniture_key(text: str) -> str:
    """The text with whitespace collapsed and digit runs replaced, so `Seite 3` and
    `Seite 4` share a key."""
    return DIGITS.sub(DIGIT_PLACEHOLDER, _WHITESPACE.sub(" ", text).strip())


def _y_clusters(lines: list[NewSourceLine], indices: list[int]) -> list[list[int]]:
    """Groups of occurrences whose yMin lie within FURNITURE_Y_TOLERANCE of the
    group's first (lowest) member."""
    ordered = sorted(indices, key=lambda i: lines[i].bbox[1])
    clusters: list[list[int]] = []
    for index in ordered:
        y = lines[index].bbox[1]
        if clusters and y - lines[clusters[-1][0]].bbox[1] <= FURNITURE_Y_TOLERANCE:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    return clusters
