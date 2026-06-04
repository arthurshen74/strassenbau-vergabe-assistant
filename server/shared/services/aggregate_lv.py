"""Aggregate LV quantities for a free-text predicate.

The one operation top-k RAG can't do: total a quantity across the LV positions that match a
predicate (e.g. "total m³ of earth removed"). Enumerate the project's LV positions, let an LLM judge
which ones belong to the predicate (membership only), then sum their `menge` (Decimal) grouped by
`einheit` in deterministic Python -- the LLM never adds anything up. Bedarfs-/Eventualpositionen are
reported separately so a conditional quantity is never folded into a headline total.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.models.lv_item import LVItem
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.aggregate_lv_models import (
    AggregateCoverage,
    AggregateLineItem,
    AggregateResult,
    AggregateTraceEntry,
    AggregateTraceStage,
    UnitSubtotal,
)
from shared.services.prompt_runner import PromptRunner

# Positionstyp values whose quantity is conditional: surfaced separately, never summed into a
# headline total (a Kalkulator decides whether they count).
CONTINGENCY_POSITIONSTYPEN = frozenset({"Bedarfsposition", "Eventualposition"})

# Unit-string variants that mean the same unit, for matching the optional `unit` filter. Grouping
# itself is by the verbatim einheit; this only normalises the caller's requested unit.
_UNIT_ALIASES = {"m3": "m³", "cbm": "m³", "m2": "m²", "qm": "m²"}


class AggregateLVService:
    def __init__(self, *, engine: AsyncEngine, llm: LLMClient) -> None:
        self._engine = engine
        self._llm = llm

    async def aggregate(
        self,
        predicate: str,
        project_uuid: UUID,
        unit: str | None = None,
        *,
        conversation_uuid: UUID | None = None,
    ) -> AggregateResult:
        trace: list[AggregateTraceEntry] = [
            AggregateTraceEntry(
                stage=AggregateTraceStage.ENTRY_STARTED,
                at=datetime.now(UTC),
                data={
                    "predicate": predicate,
                    "project_uuid": str(project_uuid),
                    "unit": unit,
                    "conversation_uuid": str(conversation_uuid)
                    if conversation_uuid is not None
                    else None,
                },
            )
        ]

        async with self._engine.connect() as conn:
            items = await LVItemRepository(conn).list_by_project(project_uuid)
            trace.append(
                AggregateTraceEntry(
                    stage=AggregateTraceStage.ITEMS_LOADED,
                    at=datetime.now(UTC),
                    data={"items_count": len(items)},
                )
            )
            membership = await PromptRunner(
                PromptVersionRepository(conn), self._llm
            ).run_lv_membership(
                predicate,
                _build_listing(items),
                project_uuid=project_uuid,
                conversation_uuid=conversation_uuid,
            )

        # Dedupe by uuid (last rationale wins) and drop any uuid the model invented.
        rationale_by_uuid = {m.lv_item_uuid: m.rationale for m in membership.matched}

        items_by_uuid = {str(i.lv_item_uuid): i for i in items}

        matched = [items_by_uuid[u] for u in rationale_by_uuid if u in items_by_uuid]

        trace.append(
            AggregateTraceEntry(
                stage=AggregateTraceStage.MATCHED,
                at=datetime.now(UTC),
                data={"matched_count": len(matched)},
            )
        )

        regular: list[LVItem] = []
        contingency: list[LVItem] = []
        for item in matched:
            bucket = contingency if item.positionstyp in CONTINGENCY_POSITIONSTYPEN else regular
            bucket.append(item)

        result = AggregateResult(
            predicate=predicate,
            unit=unit,
            per_unit=_subtotals(regular, unit),
            breakdown=[_line(i, rationale_by_uuid) for i in regular],
            bedarfs_eventual=[_line(i, rationale_by_uuid) for i in contingency],
            coverage=AggregateCoverage(matched=len(matched), total=len(items)),
        )
        trace.append(
            AggregateTraceEntry(
                stage=AggregateTraceStage.RESULT_READY,
                at=datetime.now(UTC),
                data={"result": result.model_dump(mode="json")},
            )
        )
        return result.model_copy(update={"trace": trace})


def _build_listing(items: list[LVItem]) -> str:
    """One JSON object per line (JSONL). langtext newlines and pipes survive as escaped string
    content, so they never collide with the line delimiter the way the prior `|` format let them."""
    return "\n".join(json.dumps(_item_record(i), ensure_ascii=False) for i in items)


def _item_record(item: LVItem) -> dict[str, str]:
    """The judge's view of one position. langtext_resolved is preferred (STL references expanded);
    stl_nr/hinweis are omitted when absent to keep the listing light at LV scale."""
    record = {
        "lv_item_uuid": str(item.lv_item_uuid),
        "oz": item.oz,
        "menge": str(item.menge),
        "einheit": item.einheit,
        "kurztext": item.kurztext,
        "langtext": item.langtext_resolved or item.langtext,
    }
    if item.stl_nr is not None:
        record["stl_nr"] = item.stl_nr
    if item.hinweis is not None:
        record["hinweis"] = item.hinweis
    return record
    

def _line(item: LVItem, rationale_by_uuid: dict[str, str]) -> AggregateLineItem:
    return AggregateLineItem(
        lv_item_uuid=item.lv_item_uuid,
        oz=item.oz,
        kurztext=item.kurztext,
        menge=item.menge,
        einheit=item.einheit,
        positionstyp=item.positionstyp,
        rationale=rationale_by_uuid.get(str(item.lv_item_uuid)),
    )


def _subtotals(items: list[LVItem], unit: str | None) -> list[UnitSubtotal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        totals[item.einheit] += item.menge
        counts[item.einheit] += 1
    subtotals = [
        UnitSubtotal(einheit=einheit, total=total, count=counts[einheit])
        for einheit, total in totals.items()
    ]
    if unit is not None:
        wanted = _normalize_unit(unit)
        subtotals = [s for s in subtotals if _normalize_unit(s.einheit) == wanted]
    return sorted(subtotals, key=lambda s: s.einheit)


def _normalize_unit(unit: str) -> str:
    cleaned = unit.strip().lower().replace(" ", "")
    return _UNIT_ALIASES.get(cleaned, cleaned)
