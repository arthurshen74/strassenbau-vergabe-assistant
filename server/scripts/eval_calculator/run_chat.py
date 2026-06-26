"""Score the EKT_CHAT_VALUES transcript-harvest against authored fixtures.

Each fixture (one JSON object per line) is a pre-launch chat transcript plus the values the Kalkulator
stated (name -> wert). The runner replays extract_chat_values over the transcript with the current
prompt, coerces the verbatim reads the way the graph node does, and grades name precision/recall and
value accuracy. Unlike run.py this needs no retrieval or graph -- just Postgres (the prompt) and
OpenRouter. Every emitted name is graded, so a name outside gold counts as spurious (the node would
silently drop one outside the catalog; here it is surfaced as a model error).

    python -m scripts.eval_calculator.run_chat --dataset eval/calculator/chat_values/example.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.clients.factory import build_llm_client, build_telemetry_sinks
from shared.config import settings
from shared.db.engine import make_engine
from shared.models.enums import PromptType
from shared.services.calculator.graph import CHAT_KATALOG, _coerce_decimal
from shared.services.calculator.llm_calls import extract_chat_values
from shared.services.calculator.prompts import load_calculator_prompts

from scripts.eval_calculator.grade_chat import (
    ChatFixtureResult,
    chat_fixture_to_dict,
    chat_metrics_to_dict,
    grade_chat_fixture,
    summarize_chat,
)

_DEFAULT_OUT = Path(__file__).resolve().parents[3] / "eval" / "calculator" / "results"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade EKT chat-value extraction against fixtures.")
    parser.add_argument("--dataset", type=Path, required=True, help="JSONL: {id, transcript, gold}")
    parser.add_argument("--abs-tol", default="0", help="absolute numeric tolerance (default exact)")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="results directory")
    return parser.parse_args()


def _load_fixtures(path: Path) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            fixtures.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"  skip line {n}: invalid JSON ({exc})", file=sys.stderr)
    return fixtures


def _system_assignments(zuweisungen: Any) -> dict[str, str | None]:
    """Mirror the extract_chat_values node: coerce each verbatim read to a Decimal string (or None
    when it has no number). Every emitted name is kept so the grader can flag spurious ones."""
    system: dict[str, str | None] = {}
    for z in zuweisungen:
        val = _coerce_decimal(z.wert)
        system[z.name] = None if val is None else str(val)
    return system


async def main() -> None:
    args = _parse_args()
    fixtures = _load_fixtures(args.dataset)
    if not fixtures:
        print(f"no fixtures in {args.dataset}")
        return

    engine = make_engine(settings.database_url, pool_size=2, application_name="eval-chat-values")
    sinks = build_telemetry_sinks(engine)
    llm = build_llm_client(sinks)
    try:
        async with engine.connect() as conn:
            prompts = await load_calculator_prompts(conn)
        chat_prompt = prompts[PromptType.EKT_CHAT_VALUES]

        results: list[ChatFixtureResult] = []
        for fx in fixtures:
            ergebnis, _ = await extract_chat_values(
                llm, fx["transcript"], CHAT_KATALOG, prompt=chat_prompt
            )
            system = _system_assignments(ergebnis.zuweisungen)
            result = grade_chat_fixture(
                fx["id"], fx.get("gold") or {}, system, abs_tol=args.abs_tol
            )
            results.append(result)
            correct = sum(1 for a in result.assignments if a.status == "correct")
            print(f"  {result.id}: {correct}/{len(fx.get('gold') or {})} gold values correct, "
                  f"{sum(1 for a in result.assignments if a.status == 'spurious')} spurious")

        metrics = summarize_chat(results)
        _write(args.out, args.dataset, args.abs_tol, chat_prompt.version, results, metrics)
    finally:
        await llm.aclose()
        await engine.dispose()


def _write(
    out_dir: Path,
    dataset: Path,
    abs_tol: str,
    prompt_version: int,
    results: list[ChatFixtureResult],
    metrics: Any,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows_path = out_dir / f"chat-{dataset.stem}-{stamp}.jsonl"
    summary_path = out_dir / f"chat-{dataset.stem}-{stamp}.summary.json"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(chat_fixture_to_dict(r), ensure_ascii=False) + "\n")
    summary = {
        "dataset": str(dataset),
        "generated_at": stamp,
        "abs_tol": abs_tol,
        "ekt_chat_values_version": prompt_version,
        "metrics": chat_metrics_to_dict(metrics),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEKT_CHAT_VALUES version: {prompt_version}")
    print(json.dumps(chat_metrics_to_dict(metrics), indent=2))
    print(f"\nwrote {rows_path}\n      {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
