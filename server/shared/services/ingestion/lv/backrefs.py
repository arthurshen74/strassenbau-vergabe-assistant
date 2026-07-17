"""Resolve "wie in voriger Position" back-references into langtext_resolved.

A position that reads "wie in voriger Position beschrieben jedoch ..." inherits its
predecessor's body and states only the delta. We compose `langtext_resolved` as the
predecessor's resolved body plus this position's delta, recursing through chains, while
the verbatim `langtext` is left untouched (LV_PARSE.md step 8). Positions without a
back-reference get `None`."""

from __future__ import annotations

from shared.services.ingestion.lv.types import SlicedPosition

WIE_IN_VORIGER = "wie in voriger Position"
JEDOCH_MARKER = "jedoch"
DELTA_SEP = " "


def resolve_backrefs(sliced: list[SlicedPosition]) -> dict[str, str | None]:
    """Return oz -> langtext_resolved (None when the position has no back-reference).

    Processes in document order so a predecessor is resolved before anything that links
    to it."""
    index_by_oz = {position.oz: i for i, position in enumerate(sliced)}
    resolved: dict[str, str | None] = {}

    for i, position in enumerate(sliced):
        predecessor = _predecessor(position, i, sliced, index_by_oz)
        if predecessor is None:
            resolved[position.oz] = None
            continue
        predecessor_body = resolved.get(predecessor.oz) or predecessor.langtext
        resolved[position.oz] = (
            f"{predecessor_body}{DELTA_SEP}{_delta(position.langtext)}"
        )

    return resolved


def _predecessor(
    position: SlicedPosition,
    index: int,
    sliced: list[SlicedPosition],
    index_by_oz: dict[str, int],
) -> SlicedPosition | None:
    if position.linked_oz and position.linked_oz in index_by_oz:
        return sliced[index_by_oz[position.linked_oz]]
    if WIE_IN_VORIGER.lower() in position.langtext.lower() and index > 0:
        return sliced[index - 1]
    return None


def _delta(langtext: str) -> str:
    """The part of a back-reference body that states the difference from the
    predecessor."""
    marker = langtext.lower().find(JEDOCH_MARKER)
    if marker != -1:
        return langtext[marker:].strip()
    return langtext.strip()
