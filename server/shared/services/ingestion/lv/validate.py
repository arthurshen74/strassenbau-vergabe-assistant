"""Validate the LLM segmentation against the SourceLine rows before slicing.

Hard failures (out-of-range spans, overlapping bodies, a non-monotonic numeric OZ sequence, an
unparseable quantity) raise `LVValidationError` -- the extraction is unusable. Soft issues
(a priced position missing its langtext or menge, an unknown linked_oz) are returned as warnings
for the caller to surface (LV_PARSE.md step 6)."""

from __future__ import annotations

from shared.models.source_line import SourceLine
from shared.services.ingestion.lv.types import ParsedPosition
from shared.services.ingestion.numbers import parse_german_decimal

OZ_SEP = "."


class LVValidationError(Exception):
    """The LLM segmentation is structurally invalid against the SourceLine rows."""


def validate(parsed: list[ParsedPosition], src: dict[int, SourceLine]) -> list[str]:
    """Run all checks; raise on a hard failure, return soft warnings."""
    _check_spans_in_range(parsed, src)
    _check_no_overlap(parsed)
    _check_oz_monotonic(parsed)
    _check_menge_parseable(parsed)
    return _soft_warnings(parsed)


def _check_spans_in_range(parsed: list[ParsedPosition], src: dict[int, SourceLine]) -> None:
    for position in parsed:
        for line_id in _all_line_ids(position):
            if line_id not in src:
                raise LVValidationError(
                    f"position {position.oz}: line_id {line_id} is out of range"
                )


def _check_no_overlap(parsed: list[ParsedPosition]) -> None:
    occupied: dict[int, str] = {}
    for position in parsed:
        for line_id in _body_line_ids(position):
            if line_id in occupied:
                raise LVValidationError(
                    f"line_id {line_id} claimed by both {occupied[line_id]} and {position.oz}"
                )
            occupied[line_id] = position.oz


def _check_oz_monotonic(parsed: list[ParsedPosition]) -> None:
    previous: tuple[int, ...] | None = None
    previous_oz: str | None = None
    for position in parsed:
        key = _oz_key(position.oz)
        if key is None:
            previous = None  # non-numeric OZ: can't compare; resume from the next one
            previous_oz = None
            continue
        if previous is not None and key <= previous:
            raise LVValidationError(
                f"OZ not increasing: {previous_oz} then {position.oz}"
            )
        previous = key
        previous_oz = position.oz


def _check_menge_parseable(parsed: list[ParsedPosition]) -> None:
    for position in parsed:
        if position.is_title or position.menge is None:
            continue
        try:
            parse_german_decimal(position.menge)
        except ValueError as exc:
            raise LVValidationError(f"position {position.oz}: {exc}") from exc


def _soft_warnings(parsed: list[ParsedPosition]) -> list[str]:
    known_oz = {position.oz for position in parsed}
    warnings: list[str] = []
    for position in parsed:
        if not position.is_title and position.langtext_span is None:
            warnings.append(f"position {position.oz} has no langtext")
        if not position.is_title and position.menge is None:
            warnings.append(f"position {position.oz} has no menge")
        if position.linked_oz and position.linked_oz not in known_oz:
            warnings.append(
                f"position {position.oz} links to unknown OZ {position.linked_oz}"
            )
    return warnings


def _all_line_ids(position: ParsedPosition) -> list[int]:
    ids = _body_line_ids(position)
    if position.hinweis_span is not None:
        ids.extend(range(position.hinweis_span[0], position.hinweis_span[1] + 1))
    return ids


def _body_line_ids(position: ParsedPosition) -> list[int]:
    ids = [position.kurztext_line]
    if position.langtext_span is not None:
        ids.extend(range(position.langtext_span[0], position.langtext_span[1] + 1))
    return ids


def _oz_key(oz: str) -> tuple[int, ...] | None:
    """Numeric comparison key for an OZ, or None when any segment is non-numeric."""
    segments = oz.split(OZ_SEP)
    if all(segment.isdigit() for segment in segments):
        return tuple(int(segment) for segment in segments)
    return None
