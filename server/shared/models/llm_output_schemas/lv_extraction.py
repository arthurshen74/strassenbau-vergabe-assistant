"""Structured-output schema for the LV extraction prompt.

The LLM segments a Leistungsverzeichnis: for every position and section title it returns
which `line_id`s belong to which field (kurztext / langtext / hinweis) plus the short
header tokens copied verbatim (oz / stl_nr / menge / einheit). It never reproduces the
Langtext and never emits coordinates -- deterministic code slices the verbatim text out of
the SourceLine rows afterwards (LV_PARSE.md).

`LVExtraction.positions` is a `list[LVPosition]`, which Pydantic renders with a `$ref` into
`$defs`. Strict structured output forbids `$ref` (see the registry docstring), so
`model_json_schema` is overridden to inline the defs before the schema reaches the transport.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Positionstyp values the model may assign to a priced position when the document states one.
# Section titles are flagged via `is_title` and tagged with POSITIONSTYP_TITEL by code, not here.
Positionstyp = Literal[
    "Normalposition",
    "Bedarfsposition",
    "Wahlposition",
    "Alternativposition",
    "Eventualposition",
    "Grundposition",
    "Zulageposition",
    "Stundenlohnarbeit",
]

POSITIONSTYP_TITEL = "Titel"

# Sentinel for an absent line span in the (start, end) integer fields.
NO_LINE = -1


class LVPosition(BaseModel):
    """One position or section title, expressed as line spans plus verbatim header tokens.

    Spans are inclusive `line_id` ranges into the line-numbered rendering; NO_LINE (-1)
    marks an absent span. Token fields are copied verbatim from the header line."""

    model_config = ConfigDict(extra="forbid")

    oz: str = Field(description="Ordnungszahl exactly as printed, e.g. '1.3.7'.")
    is_title: bool = Field(
        description="True for a section Titel (e.g. '1 Strassenbau') that carries no "
        "quantity; false for a priced position."
    )
    kurztext_line: int = Field(
        description="line_id of the position's header / short-text line."
    )
    langtext_start: int = Field(
        description="First line_id of the long-text body; -1 if there is none."
    )
    langtext_end: int = Field(
        description="Last line_id of the long-text body, inclusive; -1 if there is none."
    )
    hinweis_start: int = Field(
        description="First line_id of a governing Hinweis block tied to this position; "
        "-1 if none."
    )
    hinweis_end: int = Field(
        description="Last line_id of the Hinweis block, inclusive; -1 if none."
    )
    stl_nr: str | None = Field(
        description="StL-/STLB-Bau number if the header names one (e.g. '21 109-126'); "
        "else null."
    )
    menge: str | None = Field(
        description="Quantity token verbatim, keeping the German decimal comma "
        "(e.g. '25,00'); null for titles and notes."
    )
    einheit: str | None = Field(
        description="Unit token verbatim (e.g. 'm', 'm2', 'St', 'psch'); null when there "
        "is no quantity."
    )
    linked_oz: str | None = Field(
        description="When the body reads 'wie in voriger Position', the OZ of the "
        "referenced predecessor; else null."
    )
    positionstyp: Positionstyp | None = Field(
        description="The position type if the document states one explicitly; else null."
    )


class LVExtraction(BaseModel):
    """Whole-document segmentation: one entry per OZ / title, in document order."""

    model_config = ConfigDict(extra="forbid")

    positions: list[LVPosition] = Field(
        description="Every position and section title in the document, in document order."
    )

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # Inline $defs/$ref so the wire schema satisfies the strict-mode no-$ref rule.
        # Terminates because the schema is non-recursive.
        return inline_defs(super().model_json_schema(*args, **kwargs))


def inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a JSON schema with every `$ref` to `$defs` replaced inline and the
    top-level `$defs` removed. Sibling keys on a `$ref` node (e.g. a description) are kept."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref is not None:
                target = resolve(copy.deepcopy(defs[ref.split("/")[-1]]))
                siblings = {k: resolve(v) for k, v in node.items() if k != "$ref"}
                return {**target, **siblings}
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)
