"""Deterministic LV post-processing pipeline.

Consumes the LLM segmentation plus the document's SourceLine rows and produces one ResolvedItem
per position: validate, slice verbatim text + pages, resolve back-references, link the OZ
hierarchy. Everything here is pure (LV_PARSE.md step 5)."""

from __future__ import annotations

from decimal import Decimal

from shared.models.llm_output_schemas.lv_extraction import POSITIONSTYP_TITEL, LVExtraction
from shared.models.source_line import SourceLine
from shared.services.ingestion.lv.backrefs import resolve_backrefs
from shared.services.ingestion.lv.linking import link_positions
from shared.services.ingestion.lv.schema_io import to_parsed_positions
from shared.services.ingestion.lv.slice_pages import slice_positions
from shared.services.ingestion.lv.types import LinkInfo, LVParseResult, ResolvedItem, SlicedPosition
from shared.services.ingestion.lv.validate import validate
from shared.services.ingestion.numbers import parse_german_decimal

TITEL_MENGE = Decimal(0)


def run(extraction: LVExtraction, source_lines: list[SourceLine]) -> LVParseResult:
    parsed = to_parsed_positions(extraction)
    src = {line.line_id: line for line in source_lines}

    warnings = validate(parsed, src)
    sliced = slice_positions(parsed, src)
    resolved = resolve_backrefs(sliced)
    links = link_positions(sliced)

    items = [_build(position, resolved.get(position.oz), links[position.oz]) for position in sliced]
    return LVParseResult(items=items, warnings=warnings)


def _build(
    position: SlicedPosition, langtext_resolved: str | None, link: LinkInfo
) -> ResolvedItem:
    # A title carries no quantity; persist it with menge 0 and a Titel type so it is still
    # addressable by OZ and retrievable as an LV_ITEM chunk.
    langtext = position.langtext or position.kurztext
    if position.is_title:
        menge = TITEL_MENGE
        positionstyp: str | None = POSITIONSTYP_TITEL
    else:
        menge = _menge(position.menge)
        positionstyp = position.positionstyp

    return ResolvedItem(
        oz=position.oz,
        kurztext=position.kurztext,
        langtext=langtext,
        langtext_resolved=langtext_resolved,
        menge=menge,
        einheit=position.einheit or "",
        positionstyp=positionstyp,
        level=link.level,
        stl_nr=position.stl_nr,
        hinweis=position.hinweis,
        linked_oz=position.linked_oz,
        prev_oz=link.prev_oz,
        next_oz=link.next_oz,
        parent_oz=link.parent_oz,
        pages=position.pages,
        source_line_uuids=position.source_line_uuids,
    )


def _menge(token: str | None) -> Decimal:
    # Validated upstream, so this parse cannot fail here.
    if token is None:
        return TITEL_MENGE
    return parse_german_decimal(token)
