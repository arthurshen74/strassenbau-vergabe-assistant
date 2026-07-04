"""Score the EKT_CHAT_VALUES transcript-harvest against authored fixtures. Thin CLI over
shared.services.eval.chat_runner (which the worker's eval-run queue also uses): builds the
clients, prints progress, and writes per-fixture results (JSONL) + a summary keyed to the
EKT_CHAT_VALUES version. Needs only Postgres (the prompt) and OpenRouter.

    python -m scripts.eval_calculator.run_chat --dataset eval/calculator/chat_values/example.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from shared.clients.factory import build_llm_client, build_telemetry_sinks
from shared.config import settings
from shared.db.engine import make_engine
from shared.services.eval.chat_runner import ChatValuesRun, run_chat_values
from shared.services.eval.grade_chat import chat_fixture_to_dict, chat_metrics_to_dict

_DEFAULT_OUT = Path(__file__).resolve().parents[3] / "eval" / "calculator" / "results"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade EKT chat-value extraction against fixtures.")
    parser.add_argument("--dataset", type=Path, required=True, help="JSONL: {id, transcript, gold}")
    parser.add_argument("--abs-tol", default="0", help="absolute numeric tolerance (default exact)")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="results directory")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    engine = make_engine(settings.database_url, pool_size=2, application_name="eval-chat-values")
    sinks = build_telemetry_sinks(engine)
    llm = build_llm_client(sinks)

    async def emit(message: str) -> None:
        print(f"  {message}")

    try:
        run = await run_chat_values(
            engine=engine,
            llm=llm,
            dataset=args.dataset,
            abs_tol=args.abs_tol,
            emit=emit,
        )
        _write(args.out, args.dataset, args.abs_tol, run)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        await llm.aclose()
        await engine.dispose()


def _write(out_dir: Path, dataset: Path, abs_tol: str, run: ChatValuesRun) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows_path = out_dir / f"chat-{dataset.stem}-{stamp}.jsonl"
    summary_path = out_dir / f"chat-{dataset.stem}-{stamp}.summary.json"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in run.results:
            fh.write(json.dumps(chat_fixture_to_dict(r), ensure_ascii=False) + "\n")
    summary = {
        "dataset": str(dataset),
        "generated_at": stamp,
        "abs_tol": abs_tol,
        "ekt_chat_values_version": run.prompt_version,
        "metrics": chat_metrics_to_dict(run.metrics),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEKT_CHAT_VALUES version: {run.prompt_version}")
    print(json.dumps(chat_metrics_to_dict(run.metrics), indent=2))
    print(f"\nwrote {rows_path}\n      {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
