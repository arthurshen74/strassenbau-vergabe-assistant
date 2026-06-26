"""Score saved EKT ground truth: re-run each position's extraction with the current prompts and
compare to the endorsed values.

Reads calculation_ground_truth for a project, re-runs each position's extraction headlessly to its
Gate B proposals (pinning the gold recipe), grades per-variable value/found/provenance plus
classification, and writes per-position results (JSONL) + a summary keyed to the prompt versions
used -- so a prompt edit's effect on extraction accuracy is measurable. Needs the live stack
(Postgres with gold rows, Elasticsearch with the project ingested, OpenRouter).

    python -m scripts.eval_calculator.run --project <uuid> [--abs-tol 0] [--out <dir>] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_rerank_client,
    build_telemetry_sinks,
)
from shared.clients.search import SearchClient
from shared.config import settings
from shared.db.engine import make_engine
from shared.models.enums import PromptType
from shared.models.lv_item import LVItem
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.lv_items import LVItemRepository
from shared.services.calculator.graph import CALCULATOR_RETRIEVAL_CONFIG, build_graph
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.retrieval import RetrievalService

from scripts.eval_calculator.capture import capture_extraction
from scripts.eval_calculator.grade import (
    PositionResult,
    grade_position,
    metrics_to_dict,
    position_to_dict,
    summarize,
)

# The extraction prompts whose versions a run is keyed to (the LLM sites the grader exercises).
_EXTRACTION_PROMPTS = (
    PromptType.EKT_LEISTUNG_CLASSIFY,
    PromptType.EKT_CHAT_VALUES,
    PromptType.EKT_LANGTEXT_EXTRACT,
)

_DEFAULT_OUT = Path(__file__).resolve().parents[3] / "eval" / "calculator" / "results"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade EKT ground truth for one project.")
    parser.add_argument("--project", type=UUID, required=True, help="project_uuid")
    parser.add_argument("--abs-tol", default="0", help="absolute numeric tolerance (default exact)")
    parser.add_argument("--limit", type=int, default=None, help="grade at most N positions")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="results directory")
    return parser.parse_args()


def _position(item: LVItem) -> dict[str, Any]:
    return {
        "oz": item.oz,
        "kurztext": item.kurztext,
        "langtext": item.langtext_resolved or item.langtext,
        "hinweis": item.hinweis,
        "menge": str(item.menge),
        "einheit": item.einheit,
        "baustoff_code": None,
    }


async def main() -> None:
    args = _parse_args()
    if settings.calculator_mock:
        print("refusing to grade: settings.calculator_mock is on (extraction would be stubbed)",
              file=sys.stderr)
        raise SystemExit(2)

    engine = make_engine(settings.database_url, pool_size=2, application_name="eval-calculator")
    sinks = build_telemetry_sinks(engine)
    llm = build_llm_client(sinks)
    embeddings = build_embeddings_client(sinks, engine)
    search = SearchClient.from_settings()
    reranker = build_rerank_client(sinks)
    retrieval = RetrievalService(
        engine=engine, llm=llm, embeddings=embeddings, search=search, reranker=reranker
    )

    try:
        async with engine.connect() as conn:
            gold = await GroundTruthRepository(conn).list_by_project(args.project)
            prompts = await load_calculator_prompts(conn)
        if args.limit is not None:
            gold = gold[: args.limit]
        if not gold:
            print(f"no ground truth for project {args.project}")
            return

        async def retrieve(query: str) -> list[str]:
            ctx = await retrieval.retrieve_context(
                query, args.project, CALCULATOR_RETRIEVAL_CONFIG
            )
            return [c.chunk_text for c in ctx.context]

        app = build_graph(retriever=retrieve, llm=llm, prompts=prompts)

        results: list[PositionResult] = []
        for g in gold:
            async with engine.connect() as conn:
                item = await LVItemRepository(conn).get(g.lv_item_uuid)
            if item is None:
                print(f"  skip {g.oz or g.lv_item_uuid}: LV position not found", file=sys.stderr)
                continue
            system_leistung_key, proposals = await capture_extraction(
                app=app,
                thread_id=f"eval-{args.project}-{item.oz}",
                position=_position(item),
                project_uuid=args.project,
                gold_leistung_key=g.leistung_key,
                gold_bauverfahren_key=g.bauverfahren_key,
            )
            result = grade_position(
                position_id=g.oz or str(g.lv_item_uuid),
                gold_leistung_key=g.leistung_key,
                gold_variables={name: gv.model_dump() for name, gv in g.gold_variables.items()},
                system_leistung_key=system_leistung_key,
                system_proposals=proposals,
                abs_tol=args.abs_tol,
            )
            results.append(result)
            print(f"  {result.id}: leistung {'ok' if result.classification_correct else 'MISS'}, "
                  f"{sum(1 for v in result.variables if v.value_correct)}/{len(result.variables)} values")

        metrics = summarize(results)
        prompt_versions = {pt.value: prompts[pt].version for pt in _EXTRACTION_PROMPTS if pt in prompts}
        _write(args.out, args.project, args.abs_tol, prompt_versions, results, metrics)
    finally:
        await reranker.aclose()
        await embeddings.aclose()
        await llm.aclose()
        await search.close()
        await engine.dispose()


def _write(
    out_dir: Path,
    project: UUID,
    abs_tol: str,
    prompt_versions: dict[str, int],
    results: list[PositionResult],
    metrics: Any,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows_path = out_dir / f"{project}-{stamp}.jsonl"
    summary_path = out_dir / f"{project}-{stamp}.summary.json"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(position_to_dict(r), ensure_ascii=False) + "\n")
    summary = {
        "project_uuid": str(project),
        "generated_at": stamp,
        "abs_tol": abs_tol,
        "prompt_versions": prompt_versions,
        "metrics": metrics_to_dict(metrics),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nprompt versions: {prompt_versions}")
    print(json.dumps(metrics_to_dict(metrics), indent=2))
    print(f"\nwrote {rows_path}\n      {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
