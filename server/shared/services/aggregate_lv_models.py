"""Result shapes for the aggregate_lv_items tool.

The LLM judges which LV positions match a predicate; deterministic code (AggregateLVService) sums
their `menge` grouped by `einheit`. These models are what that service returns and what the agent
emits on the wire (scripts/export_schema.py exports them for the UI's AggregateResultMessage).
Contingency positions (Bedarfs-/Eventualpositionen) are surfaced separately, never folded into the
headline per-unit totals.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UnitSubtotal(BaseModel):
    """The summed quantity for one unit of measure across the matched, non-contingency positions."""

    model_config = ConfigDict(extra="forbid")

    einheit: str
    total: Decimal
    count: int


class AggregateLineItem(BaseModel):
    """One matched LV position in the itemized breakdown (so the Kalkulator can audit the total)."""

    model_config = ConfigDict(extra="forbid")

    lv_item_uuid: UUID
    oz: str
    kurztext: str
    menge: Decimal
    einheit: str
    positionstyp: str | None = None
    rationale: str | None = None


class AggregateCoverage(BaseModel):
    """How much of the LV the aggregate covers: matched positions out of the total considered."""

    model_config = ConfigDict(extra="forbid")

    matched: int
    total: int


class AggregateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: str
    unit: str | None = None
    per_unit: list[UnitSubtotal]
    breakdown: list[AggregateLineItem]
    bedarfs_eventual: list[AggregateLineItem]
    coverage: AggregateCoverage
