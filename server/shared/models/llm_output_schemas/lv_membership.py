"""Structured-output schema for the aggregate LV membership prompt.

Given a numbered listing of a project's LV positions and an aggregation predicate (e.g. "earth
removal" / "Bodenabtrag"), the model returns which positions belong to the predicate -- membership
only. It never sums, and never invents an lv_item_uuid: each returned uuid is copied verbatim from
the listing. Deterministic Python does the arithmetic afterwards (the AggregateLVService).

`LVMembership.matched` is a `list[LVMembershipItem]`, which Pydantic renders with a `$ref` into
`$defs`. Strict structured output forbids `$ref` (see the registry docstring), so `model_json_schema`
is overridden to inline the defs before the schema reaches the transport.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.models.llm_output_schemas.lv_extraction import inline_defs


class LVMembershipItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lv_item_uuid: str = Field(
        description="The lv_item_uuid of a matching position, copied verbatim from the listing."
    )
    rationale: str = Field(
        description="A short reason (a few words) why this position matches the predicate."
    )


class LVMembership(BaseModel):
    """The LV positions that match an aggregation predicate, in listing order."""

    model_config = ConfigDict(extra="forbid")

    matched: list[LVMembershipItem] = Field(
        description="Every LV position that matches the predicate. Empty when none match."
    )

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # Inline $defs/$ref so the wire schema satisfies the strict-mode no-$ref rule.
        return inline_defs(super().model_json_schema(*args, **kwargs))
