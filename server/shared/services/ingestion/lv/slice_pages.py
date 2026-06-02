"""Slice verbatim text out of SourceLine by the LLM's line spans, and map each span to pages.

Code owns the contractual text (LV_PARSE.md): the model only points at line_ids, and here we
cut the exact `line_text` out of SourceLine, join multi-line bodies, collect the covered pages,
and record the SourceLine UUIDs each position draws from."""

from __future__ import annotations

from shared.models.source_line import SourceLine
from shared.services.ingestion.lv.types import ParsedPosition, SlicedPosition

LINE_JOIN = "\n"


def slice_positions(
    parsed: list[ParsedPosition], src: dict[int, SourceLine]
) -> list[SlicedPosition]:
    return [_slice_one(position, src) for position in parsed]


def _slice_one(position: ParsedPosition, src: dict[int, SourceLine]) -> SlicedPosition:
    kurztext = src[position.kurztext_line].line_text
    langtext_lines = _span_line_ids(position.langtext_span)
    hinweis_lines = _span_line_ids(position.hinweis_span)

    langtext = LINE_JOIN.join(src[line_id].line_text for line_id in langtext_lines)
    hinweis = (
        LINE_JOIN.join(src[line_id].line_text for line_id in hinweis_lines)
        if hinweis_lines
        else None
    )

    covered = [position.kurztext_line, *langtext_lines, *hinweis_lines]
    pages = sorted({src[line_id].page for line_id in covered})
    source_line_uuids = [src[line_id].source_line_uuid for line_id in covered]

    return SlicedPosition(
        oz=position.oz,
        is_title=position.is_title,
        kurztext=kurztext,
        langtext=langtext,
        hinweis=hinweis,
        menge=position.menge,
        einheit=position.einheit,
        stl_nr=position.stl_nr,
        linked_oz=position.linked_oz,
        positionstyp=position.positionstyp,
        pages=pages,
        source_line_uuids=source_line_uuids,
    )


def _span_line_ids(span: tuple[int, int] | None) -> list[int]:
    if span is None:
        return []
    start, end = span
    return list(range(start, end + 1))
