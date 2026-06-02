"""Deterministic LV post-processing pipeline.

Consumes the LLM segmentation plus the document's SourceLine rows and produces one ResolvedItem
per position: validate, slice verbatim text + pages, resolve back-references, link the OZ
hierarchy. Everything here is pure (LV_PARSE.md step 5)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from decimal import Decimal

from shared.models.llm_output_schemas.lv_extraction import POSITIONSTYP_TITEL, LVExtraction
from shared.models.source_line import SourceLine
from shared.services.ingestion.lv.backrefs import resolve_backrefs
from shared.services.ingestion.lv.linking import link_positions
from shared.services.ingestion.lv.schema_io import to_parsed_positions
from shared.services.ingestion.lv.slice_pages import slice_positions
from shared.services.ingestion.lv.types import (
    LinkInfo,
    LVParseResult,
    ParsedPosition,
    ResolvedItem,
    SlicedPosition,
)
from shared.services.ingestion.lv.validate import validate
from shared.services.ingestion.numbers import is_placeholder_menge, parse_german_decimal

TITEL_MENGE = Decimal(0)


def run(extraction: LVExtraction, source_lines: list[SourceLine]) -> LVParseResult:
    parsed = to_parsed_positions(extraction)
    # A blank form prints an unfilled quantity as an 'xxxxxx,xx' placeholder; read it as a
    # missing menge (a soft warning) rather than letting the numeric check fail the document.
    parsed, placeholder_warnings = _drop_placeholder_menge(parsed)
    # OZ is the LV item's natural key, so the LLM emitting one OZ more than once is a single
    # position it split into fragments; coalesce those into one (union of lines, max menge,
    # last einheit) rather than failing the overlap check or colliding on persistence.
    parsed, coalesce_warnings = _coalesce_by_oz(parsed)
    # The finer lines also make a position's langtext span overshoot into the *next* position's
    # header (or a neighbour's body); trim those cross-OZ overlaps before the overlap check.
    parsed, overlap_warnings = _resolve_overlaps(parsed)
    src = {line.line_id: line for line in source_lines}

    warnings = placeholder_warnings + coalesce_warnings + overlap_warnings + validate(parsed, src)
    sliced = slice_positions(parsed, src)
    resolved = resolve_backrefs(sliced)
    links = link_positions(sliced)

    items = [_build(position, resolved.get(position.oz), links[position.oz]) for position in sliced]
    return LVParseResult(items=items, warnings=warnings)


def _drop_placeholder_menge(parsed: list[ParsedPosition]) -> tuple[list[ParsedPosition], list[str]]:
    """Null out unfilled 'xxxxxx,xx' placeholder mengen so they read as a missing quantity."""
    out: list[ParsedPosition] = []
    warnings: list[str] = []
    for position in parsed:
        if position.menge is not None and is_placeholder_menge(position.menge):
            warnings.append(f"position {position.oz}: placeholder menge {position.menge!r} dropped")
            out.append(replace(position, menge=None))
        else:
            out.append(position)
    return out, warnings


def _coalesce_by_oz(parsed: list[ParsedPosition]) -> tuple[list[ParsedPosition], list[str]]:
    """Merge entries that share an OZ into one position, preserving first-seen order."""
    groups: dict[str, list[ParsedPosition]] = {}
    order: list[str] = []
    for position in parsed:
        if position.oz not in groups:
            groups[position.oz] = []
            order.append(position.oz)
        groups[position.oz].append(position)

    coalesced: list[ParsedPosition] = []
    warnings: list[str] = []
    for oz in order:
        entries = groups[oz]
        if len(entries) == 1:
            coalesced.append(entries[0])
            continue
        warnings.append(f"coalesced {len(entries)} entries for OZ {oz}")
        coalesced.append(_merge(entries))
    return coalesced, warnings


def _resolve_overlaps(parsed: list[ParsedPosition]) -> tuple[list[ParsedPosition], list[str]]:
    """Trim a position's langtext where another OZ already owns the line.

    A kurztext line is a hard boundary that defines ownership, so a langtext line coinciding
    with another OZ's kurztext line -- or already claimed by an earlier position's langtext --
    is dropped from the later claimant (no contractual text is lost: the line stays with the
    position that owns it). Cross-OZ conflicts that can't be resolved this way (e.g. two OZs
    sharing one kurztext line) still fail loudly in validate()."""
    headers = {position.kurztext_line: position.oz for position in parsed}
    owner: dict[int, str] = {}
    resolved: list[ParsedPosition] = []
    warnings: list[str] = []
    for position in parsed:
        kept: list[int] = []
        for line_id in position.langtext_lines:
            header_oz = headers.get(line_id)
            if header_oz is not None and header_oz != position.oz:
                warnings.append(
                    f"position {position.oz}: dropped langtext line {line_id} (header of {header_oz})"
                )
                continue
            claim_oz = owner.get(line_id)
            if claim_oz is not None and claim_oz != position.oz:
                warnings.append(
                    f"position {position.oz}: dropped langtext line {line_id} "
                    f"(already claimed by {claim_oz})"
                )
                continue
            owner[line_id] = position.oz
            kept.append(line_id)
        owner[position.kurztext_line] = position.oz
        resolved.append(replace(position, langtext_lines=kept))
    return resolved, warnings


def _merge(entries: list[ParsedPosition]) -> ParsedPosition:
    """Coalesce same-OZ entries: union the body/hinweis lines (a shared line appears once),
    take the highest menge, the last einheit, and the first stated value for the rest."""
    first = entries[0]
    body: set[int] = set()
    hinweis: set[int] = set()
    for entry in entries:
        body.update(entry.langtext_lines)
        body.add(entry.kurztext_line)  # keep a fragment's header line as body content
        hinweis.update(entry.hinweis_lines)
    body.discard(first.kurztext_line)  # the chosen kurztext is not repeated in the body

    return ParsedPosition(
        oz=first.oz,
        is_title=first.is_title,
        kurztext_line=first.kurztext_line,
        langtext_lines=sorted(body),
        hinweis_lines=sorted(hinweis),
        stl_nr=_first_set(entry.stl_nr for entry in entries),
        menge=_max_menge(entries),
        einheit=_last_set(entry.einheit for entry in entries),
        linked_oz=_first_set(entry.linked_oz for entry in entries),
        positionstyp=_first_set(entry.positionstyp for entry in entries),
    )


def _first_set(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _last_set(values: Iterable[str | None]) -> str | None:
    result: str | None = None
    for value in values:
        if value:
            result = value
    return result


def _max_menge(entries: list[ParsedPosition]) -> str | None:
    """The menge token with the highest numeric value; falls back to the first stated token
    if none parse (validation then flags it)."""
    best_token: str | None = None
    best_value: Decimal | None = None
    for entry in entries:
        if entry.menge is None:
            continue
        try:
            value = parse_german_decimal(entry.menge)
        except ValueError:
            continue
        if best_value is None or value > best_value:
            best_value, best_token = value, entry.menge
    return best_token if best_token is not None else _first_set(e.menge for e in entries)


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
