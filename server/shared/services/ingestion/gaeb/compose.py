"""Compose raw GAEB LV items into the LVParseResult shape shared with the rest of
ingestion.

Takes the format readers' (D83, X83) `RawLVItem`s in document order, detects textual
back-references ("wie in voriger Position", "desgl.", "wie Pos. 01.02.0030", ...) into
`linked_oz`, and reuses the LV pipeline's back-reference resolution and OZ linking so
GAEB-parsed positions carry the same `langtext_resolved`, `level`, `parent_oz`, and
`prev_oz`/`next_oz` semantics. The readers' LV-level free text (`AddTextBlock`) and
Hinweistext nodes (`Remark`) pass through untouched. GAEB files have no pages or source
lines, so provenance fields stay empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from shared.services.ingestion.lv.backrefs import resolve_backrefs
from shared.services.ingestion.lv.linking import link_positions
from shared.services.ingestion.lv.types import (
    TITEL_MENGE,
    AddTextBlock,
    LVParseResult,
    Remark,
    SlicedPosition,
    build_resolved_item,
)
from shared.services.ingestion.numbers import DECIMAL_POINT, DECIMAL_SEP

OZ_SEGMENT_SEP = "."

# Prior-sibling references: shorthand for "same as the previous priced position".
SIBLING_BACKREF_RE = re.compile(
    r"wie\s+(?:in\s+)?(?:der\s+)?(?:vorig\w*\s+Position|Vorposition|vor\.?\s*Pos\.?)"
    r"|\bdesgl(?:eichen)?\b"
    r"|\bdito\b"
    r"|\bw\.\s?v\.",
    re.IGNORECASE,
)

# Explicit references to another position's dotted OZ, e.g. "wie Pos. 01.02.0030".
EXPLICIT_BACKREF_RE = re.compile(
    r"\bwie\s+(?:in\s+)?(?:Pos(?:ition|\.)?|OZ)\s+((?:\d+\.)+\d+(?:\.[0-9A-Za-z]+)?)",
    re.IGNORECASE,
)


class GaebParseError(Exception):
    """The file violates the GAEB exchange structure."""


@dataclass(frozen=True)
class RawLVItem:
    """One LV-Gruppe title or Teilleistung as a format reader emitted it, texts
    finalised."""

    oz: str
    is_title: bool
    kurztext: str
    langtext: str
    hinweis: str | None
    menge: Decimal | None
    einheit: str
    stl_nr: str | None
    positionstyp: str | None


def compose(
    raw_items: list[RawLVItem],
    warnings: list[str],
    add_texts: list[AddTextBlock],
    remarks: list[Remark],
) -> LVParseResult:
    _ensure_unique_oz(raw_items)
    canonical = {_canonical_oz(item.oz): item.oz for item in raw_items}

    sliced: list[SlicedPosition] = []
    prev_priced_oz: str | None = None
    for item in raw_items:
        linked_oz = None
        if not item.is_title:
            linked_oz = _linked_oz(item, prev_priced_oz, canonical, warnings)
            if item.menge is None:
                warnings.append(f"position {item.oz}: blank Menge read as 0")
        sliced.append(_to_sliced(item, linked_oz))
        if not item.is_title:
            prev_priced_oz = item.oz

    resolved = resolve_backrefs(sliced)
    links = link_positions(sliced)
    items = [
        build_resolved_item(
            position,
            item.menge if item.menge is not None else TITEL_MENGE,
            resolved.get(position.oz),
            links[position.oz],
        )
        for position, item in zip(sliced, raw_items)
    ]
    return LVParseResult(
        items=items, warnings=warnings, add_texts=add_texts, remarks=remarks
    )


def _ensure_unique_oz(raw_items: list[RawLVItem]) -> None:
    seen: set[str] = set()
    for item in raw_items:
        if item.oz in seen:
            raise GaebParseError(f"duplicate OZ {item.oz}")
        seen.add(item.oz)


def _linked_oz(
    item: RawLVItem,
    prev_priced_oz: str | None,
    canonical: dict[tuple[str, ...], str],
    warnings: list[str],
) -> str | None:
    text = f"{item.kurztext}\n{item.langtext}"
    explicit = EXPLICIT_BACKREF_RE.search(text)
    if explicit is not None:
        referenced = canonical.get(_canonical_oz(explicit.group(1)))
        if referenced is not None:
            return referenced
        warnings.append(
            f"position {item.oz}: back-reference to unknown OZ {explicit.group(1)!r}"
        )
        return None
    if SIBLING_BACKREF_RE.search(text) is not None:
        if prev_priced_oz is not None:
            return prev_priced_oz
        warnings.append(
            f"position {item.oz}: prior-sibling back-reference has no predecessor"
        )
    return None


def _canonical_oz(oz: str) -> tuple[str, ...]:
    """OZ key insensitive to zero-padding, so '01.02.0030' matches a printed
    '1.2.30'."""
    return tuple(
        str(int(segment)) if segment.isdigit() else segment.lower()
        for segment in oz.split(OZ_SEGMENT_SEP)
    )


def _to_sliced(item: RawLVItem, linked_oz: str | None) -> SlicedPosition:
    return SlicedPosition(
        oz=item.oz,
        is_title=item.is_title,
        kurztext=item.kurztext,
        langtext=item.langtext,
        hinweis=item.hinweis,
        menge=_german_token(item.menge),
        einheit=item.einheit or None,
        stl_nr=item.stl_nr,
        linked_oz=linked_oz,
        positionstyp=None if item.is_title else item.positionstyp,
        pages=[],
        source_line_uuids=[],
    )


def _german_token(menge: Decimal | None) -> str | None:
    """SlicedPosition carries menge as a German decimal token (e.g. '1,000')."""
    if menge is None:
        return None
    return str(menge).replace(DECIMAL_POINT, DECIMAL_SEP)
