"""Reflow: source_lines + layout regions -> typed, ordered, dehyphenated blocks.

Pure functions over already-loaded data; no I/O. The pipeline (design D2/D6):

1. Furniture = repetition heuristic UNION model page-header/footer labels.
2. Each remaining line is assigned to the smallest layout region containing its
   bbox center; the region's label decides the block type. Uncovered lines fall back to
   PROSE and are never dropped.
3. Consecutive lines of one region form a block; PROSE runs are additionally split
   into paragraphs where the vertical gap exceeds PARAGRAPH_GAP_FACTOR x the document's
   median line pitch (top-to-top distance).
4. Lines join with German dehyphenation: a line-end hyphen joins the next line
   dropping the hyphen when it starts lowercase (justification break), keeping it when
   it starts uppercase (compound like "SRT-Pendel").
5. A block ending without terminal punctuation merges with the next page's first
   block when that block starts lowercase (sentence spanning a page break).

Every block records the ordered line_ids it was built from (provenance).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from shared.models.enums import BlockType
from shared.models.nlp import LayoutRegion, ReflowedBlock, ReflowResult
from shared.models.source_line import SourceLine
from shared.services.nlp.layout import (
    LABEL_CAPTION,
    LABEL_DOCUMENT_INDEX,
    LABEL_FOOTNOTE,
    LABEL_LIST_ITEM,
    LABEL_PAGE_FOOTER,
    LABEL_PAGE_HEADER,
    LABEL_SECTION_HEADER,
    LABEL_TABLE,
    LABEL_TITLE,
)

# Repetition heuristic: a normalized line repeating on at least this fraction of pages
# (and at least MIN_REPEAT_PAGES) is page furniture.
FURNITURE_PAGE_FRACTION = 0.5
MIN_REPEAT_PAGES = 3
# y-position bucket size in points for the repetition key.
FURNITURE_Y_BUCKET_PT = 5.0

# Paragraph break: gap between consecutive lines exceeding this fraction of the
# document's median line pitch (top-to-top distance of consecutive lines).
PARAGRAPH_GAP_FACTOR = 0.8

FURNITURE_LABELS = frozenset({LABEL_PAGE_HEADER, LABEL_PAGE_FOOTER})

_LABEL_TO_BLOCK_TYPE = {
    LABEL_SECTION_HEADER: BlockType.HEADING,
    LABEL_TITLE: BlockType.HEADING,
    LABEL_LIST_ITEM: BlockType.LIST_ITEM,
    LABEL_TABLE: BlockType.TABLE,
    LABEL_DOCUMENT_INDEX: BlockType.TABLE,
    LABEL_CAPTION: BlockType.CAPTION,
    LABEL_FOOTNOTE: BlockType.FOOTNOTE,
}

_TERMINAL_PUNCTUATION = (".", "!", "?", ":", ";")


def reflow_document(
    lines: list[SourceLine], regions: list[LayoutRegion]
) -> ReflowResult:
    """Full reflow of one document's lines against its layout regions."""
    furniture_ids = _heuristic_furniture(lines) | _model_furniture(lines, regions)
    line_types: dict[int, BlockType] = {
        line.line_id: BlockType.FURNITURE
        for line in lines
        if line.line_id in furniture_ids
    }

    content = [line for line in lines if line.line_id not in furniture_ids]
    runs = _assign_runs(content, regions)
    for run in runs:
        for line in run.lines:
            line_types[line.line_id] = run.block_type

    paragraph_gap = PARAGRAPH_GAP_FACTOR * _median_line_pitch(lines)
    blocks: list[ReflowedBlock] = []
    for run in runs:
        if run.block_type is BlockType.PROSE:
            for paragraph in _split_paragraphs(run.lines, paragraph_gap):
                blocks.append(_build_block(len(blocks), run.block_type, paragraph))
        else:
            blocks.append(_build_block(len(blocks), run.block_type, run.lines))

    blocks = _merge_cross_page(blocks)
    return ReflowResult(blocks=blocks, line_types=line_types)


# --- furniture ------------------------------------------------------------------


def _heuristic_furniture(lines: list[SourceLine]) -> set[int]:
    """line_ids whose normalized text + y-bucket repeats across enough pages."""
    n_pages = max((line.page for line in lines), default=0)
    if n_pages < MIN_REPEAT_PAGES:
        return set()
    pages_by_key: dict[tuple[str, int], set[int]] = defaultdict(set)
    for line in lines:
        pages_by_key[_furniture_key(line)].add(line.page)
    threshold = max(MIN_REPEAT_PAGES, int(n_pages * FURNITURE_PAGE_FRACTION))
    repeated = {key for key, pages in pages_by_key.items() if len(pages) >= threshold}
    return {line.line_id for line in lines if _furniture_key(line) in repeated}


def _furniture_key(line: SourceLine) -> tuple[str, int]:
    # Digit runs collapse to one '#' so 'Seite 1/14' and 'Seite 10/14' collide.
    normalized = re.sub(r"\d+", "#", line.line_text)
    return (normalized, int(line.bbox[1] / FURNITURE_Y_BUCKET_PT))


def _model_furniture(lines: list[SourceLine], regions: list[LayoutRegion]) -> set[int]:
    furniture_regions = [r for r in regions if r.label in FURNITURE_LABELS]
    return {
        line.line_id
        for line in lines
        if any(_center_in(line, r) for r in furniture_regions if r.page == line.page)
    }


def _center_in(line: SourceLine, region: LayoutRegion) -> bool:
    cx = (line.bbox[0] + line.bbox[2]) / 2
    cy = (line.bbox[1] + line.bbox[3]) / 2
    x1, y1, x2, y2 = region.bbox
    return x1 <= cx <= x2 and y1 <= cy <= y2


# --- region assignment and runs ---------------------------------------------------


@dataclass
class _Run:
    """Consecutive lines sharing one region (or the uncovered-PROSE fallback)."""

    block_type: BlockType
    region_index: int | None
    lines: list[SourceLine] = field(default_factory=list)


def _assign_runs(lines: list[SourceLine], regions: list[LayoutRegion]) -> list[_Run]:
    by_page: dict[int, list[tuple[int, LayoutRegion]]] = defaultdict(list)
    for index, region in enumerate(regions):
        if region.label not in FURNITURE_LABELS:
            by_page[region.page].append((index, region))

    runs: list[_Run] = []
    for line in lines:
        index = _smallest_containing(line, by_page[line.page])
        block_type = (
            _region_block_type(regions[index]) if index is not None else BlockType.PROSE
        )
        current = runs[-1] if runs else None
        if (
            current is None
            or current.region_index != index
            or current.block_type != block_type
        ):
            current = _Run(block_type=block_type, region_index=index)
            runs.append(current)
        current.lines.append(line)
    return runs


def _smallest_containing(
    line: SourceLine, candidates: list[tuple[int, LayoutRegion]]
) -> int | None:
    best: int | None = None
    best_area = float("inf")
    for index, region in candidates:
        if _center_in(line, region):
            x1, y1, x2, y2 = region.bbox
            area = (x2 - x1) * (y2 - y1)
            if area < best_area:
                best, best_area = index, area
    return best


def _region_block_type(region: LayoutRegion) -> BlockType:
    return _LABEL_TO_BLOCK_TYPE.get(region.label, BlockType.PROSE)


# --- paragraphs and reflow ----------------------------------------------------------


def _median_line_pitch(lines: list[SourceLine]) -> float:
    """Median top-to-top distance of consecutive lines on the same page."""
    pitches = [
        after.bbox[1] - before.bbox[1]
        for before, after in zip(lines, lines[1:])
        if after.page == before.page and after.bbox[1] > before.bbox[1]
    ]
    if not pitches:
        return 12.0  # a typical single-spaced pitch; only hit on near-empty documents
    pitches.sort()
    # Lower median: paragraph-gap outliers must not drag the estimate up.
    return pitches[(len(pitches) - 1) // 2]


def _split_paragraphs(
    lines: list[SourceLine], gap_threshold: float
) -> list[list[SourceLine]]:
    paragraphs: list[list[SourceLine]] = []
    for line in lines:
        previous = paragraphs[-1][-1] if paragraphs and paragraphs[-1] else None
        starts_new = (
            previous is None
            or line.page != previous.page
            or (line.bbox[1] - previous.bbox[3]) > gap_threshold
        )
        if starts_new and not _continues_page_break(previous, line):
            paragraphs.append([])
        paragraphs[-1].append(line)
    return paragraphs


def _continues_page_break(previous: SourceLine | None, line: SourceLine) -> bool:
    """A page turn inside a paragraph: previous page ends mid-sentence, next starts
    lowercase."""
    if previous is None or line.page <= previous.page:
        return False
    return _joins_previous(previous.line_text, line.line_text)


def _joins_previous(previous_text: str, next_text: str) -> bool:
    # No lowercase test on the continuation: German capitalizes nouns, so a sentence
    # resuming after a page turn regularly starts uppercase ("... mit den wesentlichen"
    # -> "Angaben über den Baufortschritt").
    del next_text
    if previous_text.endswith("-"):
        return True
    return not previous_text.endswith(_TERMINAL_PUNCTUATION)


def _build_block(
    block_id: int, block_type: BlockType, lines: list[SourceLine]
) -> ReflowedBlock:
    return ReflowedBlock(
        block_id=block_id,
        block_type=block_type,
        text=_join_lines([line.line_text for line in lines]),
        page_start=lines[0].page,
        page_end=lines[-1].page,
        line_ids=[line.line_id for line in lines],
    )


def _join_lines(texts: list[str]) -> str:
    joined = texts[0]
    for text in texts[1:]:
        if joined.endswith("-") and text[:1].islower():
            joined = joined[:-1] + text  # justification break: drop the hyphen
        elif joined.endswith("-"):
            joined = joined + text  # compound hyphen: keep it, no space
        else:
            joined = joined + " " + text
    return joined


# --- cross-page merge
# ------------------------------------------------------------------


def _merge_cross_page(blocks: list[ReflowedBlock]) -> list[ReflowedBlock]:
    """Merge a block ending mid-sentence with the next page's first block."""
    merged: list[ReflowedBlock] = []
    for block in blocks:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.block_type == block.block_type
            and block.page_start > previous.page_end
            and _joins_previous(previous.text, block.text)
        ):
            merged[-1] = ReflowedBlock(
                block_id=previous.block_id,
                block_type=previous.block_type,
                text=_join_lines([previous.text, block.text]),
                page_start=previous.page_start,
                page_end=block.page_end,
                line_ids=previous.line_ids + block.line_ids,
            )
        else:
            merged.append(block)
    return _renumber(merged)


def _renumber(blocks: list[ReflowedBlock]) -> list[ReflowedBlock]:
    return [
        block.model_copy(update={"block_id": index})
        for index, block in enumerate(blocks)
    ]
