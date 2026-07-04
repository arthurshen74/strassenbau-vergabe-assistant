"""Headless calculator-gold eval: re-run each gold position's extraction with the current
prompts and grade it against the saved ground truth (pinning the gold recipe at Gate 2, so
extraction quality is decoupled from classification, which is scored separately).

The runner is harness-agnostic: progress goes through the async `emit` callback, results come
back as a value. The CLI (scripts.eval_calculator.run) prints and writes result files; the
worker's eval-run queue records events and result rows. Needs the live stack (Postgres gold,
Elasticsearch with the project ingested, OpenRouter).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search.client import SearchClient
from shared.config import settings
from shared.models.enums import PromptType
from shared.models.lv_item import LVItem
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.lv_items import LVItemRepository
from shared.services.calculator.graph import CALCULATOR_RETRIEVAL_CONFIG, build_graph
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.eval.capture import capture_extraction
from shared.services.eval.grade import (
    Metrics,
    PositionResult,
    grade_position,
    summarize,
)
from shared.services.kalkulation_v2.leistung_bauverfahren import kandidaten
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.retrieval import RetrievalService

Emit = Callable[[str], Awaitable[None]]

# The extraction prompts whose versions a run is keyed to (the LLM sites the grader exercises).
EXTRACTION_PROMPTS = (
    PromptType.EKT_LEISTUNG_CLASSIFY,
    PromptType.EKT_CHAT_VALUES,
    PromptType.EKT_LANGTEXT_EXTRACT,
)


@dataclass(frozen=True)
class CalculatorGoldRun:
    results: list[PositionResult]
    metrics: Metrics
    prompt_versions: dict[str, int]
    skipped: int


def stale_gold_reason(leistung_key: str, bauverfahren_key: str | None) -> str | None:
    """A gold recipe that no longer exists in the catalog cannot be pinned at Gate 2 (the graph
    rejects it); mirrors waehle_bauverfahren's validation. Returns the skip reason, or None."""
    if leistung_key not in LEISTUNGEN:
        return f"gold leistung_key {leistung_key!r} not in catalog"
    if bauverfahren_key is not None and bauverfahren_key not in kandidaten(leistung_key):
        return f"gold bauverfahren_key {bauverfahren_key!r} not a candidate for {leistung_key!r}"
    return None


def position_payload(item: LVItem) -> dict[str, Any]:
    return {
        "oz": item.oz,
        "kurztext": item.kurztext,
        "langtext": item.langtext_resolved or item.langtext,
        "hinweis": item.hinweis,
        "menge": str(item.menge),
        "einheit": item.einheit,
        "baustoff_code": None,
    }


async def run_calculator_gold(
    *,
    engine: AsyncEngine,
    llm: LLMClient,
    embeddings: EmbeddingsClient,
    search: SearchClient,
    reranker: RerankClient,
    project_uuid: UUID,
    abs_tol: str = "0",
    limit: int | None = None,
    emit: Emit,
) -> CalculatorGoldRun:
    if settings.calculator_mock:
        raise RuntimeError(
            "refusing to grade: settings.calculator_mock is on (extraction would be stubbed)"
        )
    retrieval = RetrievalService(
        engine=engine, llm=llm, embeddings=embeddings, search=search, reranker=reranker
    )
    async with engine.connect() as conn:
        gold = await GroundTruthRepository(conn).list_by_project(project_uuid)
        prompts = await load_calculator_prompts(conn)
    if limit is not None:
        gold = gold[:limit]
    prompt_versions = {
        pt.value: prompts[pt].version for pt in EXTRACTION_PROMPTS if pt in prompts
    }

    async def retrieve(query: str) -> list[str]:
        ctx = await retrieval.retrieve_context(
            query, project_uuid, CALCULATOR_RETRIEVAL_CONFIG
        )
        return [c.chunk_text for c in ctx.context]

    app = build_graph(retriever=retrieve, llm=llm, prompts=prompts)

    results: list[PositionResult] = []
    skipped = 0
    for g in gold:
        stale = stale_gold_reason(g.leistung_key, g.bauverfahren_key)
        if stale:
            await emit(f"skip {g.oz or g.lv_item_uuid}: {stale}")
            skipped += 1
            continue
        async with engine.connect() as conn:
            item = await LVItemRepository(conn).get(g.lv_item_uuid)
        if item is None:
            await emit(f"skip {g.oz or g.lv_item_uuid}: LV position not found")
            skipped += 1
            continue
        system_leistung_key, system_bauverfahren_key, proposals = await capture_extraction(
            app=app,
            thread_id=f"eval-{project_uuid}-{item.oz}",
            position=position_payload(item),
            project_uuid=project_uuid,
            gold_leistung_key=g.leistung_key,
            gold_bauverfahren_key=g.bauverfahren_key,
        )
        result = grade_position(
            position_id=g.oz or str(g.lv_item_uuid),
            gold_leistung_key=g.leistung_key,
            gold_variables={name: gv.model_dump() for name, gv in g.gold_variables.items()},
            system_leistung_key=system_leistung_key,
            system_proposals=proposals,
            gold_bauverfahren_key=g.bauverfahren_key,
            system_bauverfahren_key=system_bauverfahren_key,
            abs_tol=abs_tol,
        )
        results.append(result)
        bv = ("n/a" if result.bauverfahren_correct is None
              else "ok" if result.bauverfahren_correct else "MISS")
        await emit(
            f"{result.id}: leistung {'ok' if result.classification_correct else 'MISS'}, "
            f"bv {bv}, "
            f"{sum(1 for v in result.variables if v.value_correct)}/{len(result.variables)} values"
        )

    if skipped:
        await emit(f"skipped {skipped} of {len(gold)} gold position(s) — re-confirm stale gold")
    return CalculatorGoldRun(
        results=results,
        metrics=summarize(results),
        prompt_versions=prompt_versions,
        skipped=skipped,
    )
