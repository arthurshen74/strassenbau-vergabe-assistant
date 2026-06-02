"""Derive the OZ hierarchy and ordering links.

`level` is the OZ depth; `parent_oz` is the nearest enclosing OZ that actually exists;
`prev_oz`/`next_oz` chain the priced positions in document order (titles are not part of the
prev/next chain) (LV_PARSE.md step 9)."""

from __future__ import annotations

from shared.services.ingestion.lv.types import LinkInfo, SlicedPosition

OZ_SEP = "."


def link_positions(sliced: list[SlicedPosition]) -> dict[str, LinkInfo]:
    oz_set = {position.oz for position in sliced}
    priced = [position.oz for position in sliced if not position.is_title]
    prev_of, next_of = _neighbours(priced)

    return {
        position.oz: LinkInfo(
            level=_level(position.oz),
            parent_oz=_parent_oz(position.oz, oz_set),
            prev_oz=prev_of.get(position.oz),
            next_oz=next_of.get(position.oz),
        )
        for position in sliced
    }


def _level(oz: str) -> int:
    return len(oz.split(OZ_SEP))


def _parent_oz(oz: str, oz_set: set[str]) -> str | None:
    """The nearest ancestor OZ that exists: drop trailing segments until one is found."""
    segments = oz.split(OZ_SEP)
    for cut in range(len(segments) - 1, 0, -1):
        candidate = OZ_SEP.join(segments[:cut])
        if candidate in oz_set:
            return candidate
    return None


def _neighbours(priced: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    prev_of: dict[str, str] = {}
    next_of: dict[str, str] = {}
    for i, oz in enumerate(priced):
        if i > 0:
            prev_of[oz] = priced[i - 1]
        if i < len(priced) - 1:
            next_of[oz] = priced[i + 1]
    return prev_of, next_of
