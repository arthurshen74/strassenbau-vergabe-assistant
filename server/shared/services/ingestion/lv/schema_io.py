"""Adapter from the LLM wire schema (LVExtraction) to the internal ParsedPosition type.

Isolating this keeps the rest of post-processing independent of the on-the-wire shape:
if the extraction schema changes, only this module follows."""

from __future__ import annotations

from shared.models.llm_output_schemas.lv_extraction import (
    NO_LINE,
    LVExtraction,
    LVPosition,
)
from shared.services.ingestion.lv.types import ParsedPosition


def to_parsed_positions(extraction: LVExtraction) -> list[ParsedPosition]:
    return [_to_parsed(position) for position in extraction.positions]


def _to_parsed(position: LVPosition) -> ParsedPosition:
    return ParsedPosition(
        oz=position.oz,
        is_title=position.is_title,
        kurztext_line=position.kurztext_line,
        langtext_lines=_lines(position.langtext_start, position.langtext_end),
        hinweis_lines=_lines(position.hinweis_start, position.hinweis_end),
        stl_nr=position.stl_nr,
        menge=position.menge,
        einheit=position.einheit,
        linked_oz=position.linked_oz,
        positionstyp=position.positionstyp,
    )


def _lines(start: int, end: int) -> list[int]:
    if start == NO_LINE or end == NO_LINE:
        return []
    return list(range(start, end + 1))
