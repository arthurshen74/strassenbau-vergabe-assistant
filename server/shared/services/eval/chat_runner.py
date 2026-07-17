"""Headless chat-value eval: replay EKT_CHAT_VALUES over authored fixtures and grade the
harvested assignments. Unlike the calculator runner this needs no retrieval or graph —
just Postgres (the prompt) and OpenRouter.

The runner is harness-agnostic (async `emit` for progress, results as a value); the CLI
and the worker's eval-run queue are its two harnesses. Fixture paths resolve against the
repo root, which the Docker image mirrors (eval/ is copied next to server/).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.models.enums import PromptType
from shared.services.calculator.graph import _coerce_decimal, chat_katalog
from shared.services.calculator.llm_calls import extract_chat_values
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.eval.grade_chat import (
    ChatFixtureResult,
    ChatMetrics,
    grade_chat_fixture,
    summarize_chat,
)

Emit = Callable[[str], Awaitable[None]]

# repo root: <root>/server/shared/services/eval/chat_runner.py
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CHAT_DATASET = "eval/calculator/chat_values/example.jsonl"


@dataclass(frozen=True)
class ChatValuesRun:
    results: list[ChatFixtureResult]
    metrics: ChatMetrics
    prompt_version: int


def resolve_dataset(path_str: str) -> Path:
    """A relative dataset path is anchored at the repo root (same layout on host and
    image)."""
    path = Path(path_str)
    return path if path.is_absolute() else _REPO_ROOT / path


def load_fixtures(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """One JSON object per line; // comment lines ignored. Returns (fixtures,
    warnings)."""
    fixtures: list[dict[str, Any]] = []
    warnings: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            fixtures.append(json.loads(line))
        except json.JSONDecodeError as exc:
            warnings.append(f"skip line {n}: invalid JSON ({exc})")
    return fixtures, warnings


def system_assignments(zuweisungen: Any) -> dict[str, str | None]:
    """Mirror the extract_chat_values node: coerce each verbatim read to a Decimal
    string (or None when it has no number). Every emitted name is kept so the grader can
    flag spurious ones."""
    system: dict[str, str | None] = {}
    for z in zuweisungen:
        val = _coerce_decimal(z.wert)
        system[z.name] = None if val is None else str(val)
    return system


async def run_chat_values(
    *,
    engine: AsyncEngine,
    llm: LLMClient,
    dataset: Path,
    abs_tol: str = "0",
    emit: Emit,
) -> ChatValuesRun:
    fixtures, warnings = load_fixtures(dataset)
    for w in warnings:
        await emit(w)
    if not fixtures:
        raise ValueError(f"no fixtures in {dataset}")

    async with engine.connect() as conn:
        prompts = await load_calculator_prompts(conn)
    chat_prompt = prompts[PromptType.EKT_CHAT_VALUES]

    results: list[ChatFixtureResult] = []
    for fx in fixtures:
        ergebnis, _ = await extract_chat_values(
            llm, fx["transcript"], chat_katalog(), prompt=chat_prompt
        )
        system = system_assignments(ergebnis.zuweisungen)
        result = grade_chat_fixture(
            fx["id"], fx.get("gold") or {}, system, abs_tol=abs_tol
        )
        results.append(result)
        correct = sum(1 for a in result.assignments if a.status == "correct")
        spurious = sum(1 for a in result.assignments if a.status == "spurious")
        await emit(
            f"{result.id}: {correct}/{len(fx.get('gold') or {})} gold values correct, "
            f"{spurious} spurious"
        )

    return ChatValuesRun(
        results=results,
        metrics=summarize_chat(results),
        prompt_version=chat_prompt.version,
    )
