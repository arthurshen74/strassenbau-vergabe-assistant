"""Score saved EKT ground truth: re-run each position's extraction with the current
prompts and compare to the endorsed values. Thin CLI over
shared.services.eval.calculator_runner (which the worker's eval-run queue also uses):
builds the clients, prints progress, and writes per-position results (JSONL) + a summary
keyed to the prompt versions used. Needs the live stack (Postgres with gold rows,
Elasticsearch with the project ingested, OpenRouter).

    python -m scripts.eval_calculator.run --project <uuid> [--abs-tol 0] [--out <dir>]
    [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
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
from shared.services.eval.calculator_runner import (
    CalculatorGoldRun,
    run_calculator_gold,
)
from shared.services.eval.grade import metrics_to_dict, position_to_dict

_DEFAULT_OUT = Path(__file__).resolve().parents[3] / "eval" / "calculator" / "results"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grade EKT ground truth for one project."
    )
    parser.add_argument("--project", type=UUID, required=True, help="project_uuid")
    parser.add_argument(
        "--abs-tol", default="0", help="absolute numeric tolerance (default exact)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="grade at most N positions"
    )
    parser.add_argument(
        "--out", type=Path, default=_DEFAULT_OUT, help="results directory"
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    engine = make_engine(
        settings.database_url, pool_size=2, application_name="eval-calculator"
    )
    sinks = build_telemetry_sinks(engine)
    llm = build_llm_client(sinks)
    embeddings = build_embeddings_client(sinks, engine)
    search = SearchClient.from_settings()
    reranker = build_rerank_client(sinks)

    async def emit(message: str) -> None:
        print(f"  {message}")

    try:
        run = await run_calculator_gold(
            engine=engine,
            llm=llm,
            embeddings=embeddings,
            search=search,
            reranker=reranker,
            project_uuid=args.project,
            abs_tol=args.abs_tol,
            limit=args.limit,
            emit=emit,
        )
        if not run.results and run.skipped == 0:
            print(f"no ground truth for project {args.project}")
            return
        if not run.results:
            print("nothing gradeable")
            return
        _write(args.out, args.project, args.abs_tol, run)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        await reranker.aclose()
        await embeddings.aclose()
        await llm.aclose()
        await search.close()
        await engine.dispose()


def _write(out_dir: Path, project: UUID, abs_tol: str, run: CalculatorGoldRun) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows_path = out_dir / f"{project}-{stamp}.jsonl"
    summary_path = out_dir / f"{project}-{stamp}.summary.json"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in run.results:
            fh.write(json.dumps(position_to_dict(r), ensure_ascii=False) + "\n")
    summary = {
        "project_uuid": str(project),
        "generated_at": stamp,
        "abs_tol": abs_tol,
        "prompt_versions": run.prompt_versions,
        "metrics": metrics_to_dict(run.metrics),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nprompt versions: {run.prompt_versions}")
    print(json.dumps(metrics_to_dict(run.metrics), indent=2))
    print(f"\nwrote {rows_path}\n      {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
