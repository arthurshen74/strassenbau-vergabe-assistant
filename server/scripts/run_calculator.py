"""Run the EKT position-calculation agent on a real LV position from the command line.

A thin harness over shared/services/calculator: it loads one LV position from the
project's LV document, wires the agent's retrieval seam to RetrievalService, runs the
LangGraph app, and walks the two HITL interrupts interactively (Gate A method review,
Gate B variable review). The whole run is traced to Phoenix (docker-compose `phoenix`).

    python -m scripts.run_calculator --project <uuid> --oz 01.02.0006 \
        --mock --leistung L_FRAESEN --set tiefe_cm=4 --set fraesgut_klasse=1

--mock skips the LLM/RAG seams: `--leistung` supplies the Leistung the mock classifier
returns, and `--set name=value` pre-pins chat values (precedence source 0); the rest of
the pipeline (both gates, the deterministic compute) runs unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any
from uuid import UUID

from langgraph.types import Command

from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_rerank_client,
    build_telemetry_sinks,
)
from shared.clients.search import SearchClient
from shared.clients.tracing import setup_phoenix_tracing
from shared.config import settings
from shared.db.engine import make_engine
from shared.models.lv_item import LVItem
from shared.repositories.lv_items import LVItemRepository
from shared.services.calculator.graph import (
    CALCULATOR_RETRIEVAL_CONFIG,
    POSITION_LEISTUNG_HINT,
    REASONING_LLM,
    REASONING_NARRATION,
    build_graph,
)
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.calculator.state import (
    STAGE_LEISTUNG_BV_REVIEW,
    STAGE_MATERIAL_REVIEW,
)
from shared.services.retrieval import RetrievalService

PHOENIX_PROJECT = "ekt-calculator"
PROVIDER_REASONING_PREVIEW = 400


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the EKT position-calculation agent on one LV position."
    )
    parser.add_argument("--project", type=UUID, required=True, help="project_uuid")
    parser.add_argument("--oz", required=True, help="Ordnungszahl, e.g. 01.02.0006")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="skip the LLM/RAG seams; use --leistung and --set",
    )
    parser.add_argument(
        "--leistung", help="mock: the Leistung key the classifier returns"
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="mock: pre-pin a chat value (source 0); repeatable",
    )
    parser.add_argument("--no-trace", action="store_true", help="skip Phoenix tracing")
    return parser.parse_args()


def _vorgaben(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        out[name.strip()] = value.strip()
    return out


async def main() -> None:
    args = _parse_args()
    if not args.no_trace:
        setup_phoenix_tracing(PHOENIX_PROJECT)
    if args.mock:
        settings.calculator_mock = True

    engine = make_engine(
        settings.database_url, pool_size=2, application_name="run-calculator"
    )
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
            item = await LVItemRepository(conn).get_by_project_and_oz(
                args.project, args.oz
            )
        if item is None:
            print(
                f"no LV position {args.oz} in project {args.project}", file=sys.stderr
            )
            raise SystemExit(1)

        async def retrieve(query: str) -> list[str]:
            ctx = await retrieval.retrieve_context(
                query, args.project, CALCULATOR_RETRIEVAL_CONFIG
            )
            return [c.chunk_text for c in ctx.context]

        prompts: dict = {}
        if not args.mock:
            async with engine.connect() as conn:
                prompts = await load_calculator_prompts(conn)
        app = build_graph(
            retriever=None if args.mock else retrieve, llm=llm, prompts=prompts
        )
        cfg = {"configurable": {"thread_id": f"ekt-{args.project}-{args.oz}"}}

        position = _position(item)
        if args.leistung:
            position[POSITION_LEISTUNG_HINT] = args.leistung
        print(f"position {item.oz}: {item.kurztext} — {item.menge} {item.einheit}")
        pending = await _stream(
            app,
            cfg,
            {
                "position": position,
                "project_uuid": args.project,
                "vorgaben": _vorgaben(args.set),
            },
        )
        while pending is not None:
            command = await _prompt_for_resume(pending)
            pending = await _stream(app, cfg, command)

        _print_state((await app.aget_state(cfg)).values)
    finally:
        await reranker.aclose()
        await embeddings.aclose()
        await llm.aclose()
        await search.close()
        await engine.dispose()


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


async def _stream(app: Any, cfg: dict, payload: Any) -> dict | None:
    """Run until the next interrupt or completion, printing reasoning live. Returns the
    interrupt payload to resume from, or None when the run ends."""
    pending = None
    async for update in app.astream(payload, cfg, stream_mode="updates"):
        if "__interrupt__" in update:
            pending = update["__interrupt__"][0].value
            continue
        for node_output in update.values():
            outputs = node_output if isinstance(node_output, list) else [node_output]
            for output in outputs:
                if isinstance(output, dict):
                    for entry in output.get("reasoning_log") or []:
                        _print_reasoning(entry)
    return pending


def _print_reasoning(entry: dict) -> None:
    if entry["kind"] == REASONING_NARRATION:
        print(f"[agent] {entry['text']}")
    elif entry["kind"] == REASONING_LLM:
        print(f"    - {entry['text']}")
    else:  # provider reasoning summary
        text = " ".join(entry["text"].split())
        if len(text) > PROVIDER_REASONING_PREVIEW:
            text = text[:PROVIDER_REASONING_PREVIEW].rstrip() + "..."
        print(f"    (model reasoning) {text}")


async def _prompt_for_resume(payload: dict) -> Command:
    stage = payload.get("stage")
    if stage == STAGE_LEISTUNG_BV_REVIEW:
        print("\nGRAPH PAUSED: Gate 2 — Leistung + Bauverfahren")
        print(f"  Leistung    : {payload['leistung_key']} ({payload['leistung_name']})")
        print(f"  Kandidaten  : {', '.join(payload['bauverfahren_kandidaten'])}")
        default = payload["bauverfahren_default"]
        answer = await _prompt(f"  Bauverfahren [{default}]> ")
        return Command(resume={"bauverfahren_key": answer or default})

    if stage == STAGE_MATERIAL_REVIEW:
        print("\nGRAPH PAUSED: Gate 3 — Material")
        vorschlag = payload.get("baustoff_vorschlag") or {}
        default = vorschlag.get("code")
        print(
            f"  Vorschlag   : {default} ({vorschlag.get('name')}) @ "
            f"{vorschlag.get('konfidenz')}"
        )
        answer = await _prompt(f"  Baustoff [{default}]> ")
        return Command(resume={"baustoff_code": answer or default})

    print("\nGRAPH PAUSED: Gate 4 — machines + supplier + variables")
    overrides: dict[str, str] = {}
    for v in payload["surfaced"]:
        flag = " [HOCHRISIKO]" if v["hochrisiko"] else ""
        print(
            f"\n  {v['name']} = {v['wert']} {v['einheit'] or ''}  "
            f"({v['quelle'] or 'ungelöst'}){flag}"
        )
        print(f"    {v['bezeichnung']}")
        answer = await _prompt(f"  {v['name']} [enter = accept]> ")
        if answer:
            overrides[v["name"]] = answer
    print(f"\n  ({len(payload['collapsed'])} Sätze/Stammdaten vorab akzeptiert)")
    return Command(resume={"overrides": overrides})


async def _prompt(label: str) -> str:
    return (await asyncio.to_thread(input, label)).strip()


def _print_state(state: dict) -> None:
    ekt = state.get("ekt_zeile")
    if ekt is None:
        print("\n(no EKT — see warnings)")
    else:
        print(f"\nEKT: {ekt['leistung']} über {ekt['bauverfahren']}")
        print(
            f"  EP {ekt['ep_eur']} EUR/{ekt['einheit']}  ·  GP {ekt['gp_eur']} EUR "
            f"({ekt['menge']} {ekt['einheit']})"
        )
        for k in ekt["kostenlinien"]:
            print(
                f"    {k['kostenart']:12} {k['variable']:26} {k['betrag_eur']:>12} EUR "
                f"({k['quelle']})"
            )
    print("\nNachweistabelle:")
    for n in state.get("nachweis_tabelle", []):
        ausdruck = f"  = {n['ausdruck']}" if n.get("ausdruck") else ""
        print(
            f"  {n['name']:30} {n['wert']:>14} {n['einheit'] or '':6} "
            f"[{n['quelle']}]{ausdruck}"
        )
    for w in state.get("warnungen", []):
        print(f"  WARNUNG: {w}")
    if state.get("beschreibung"):
        print(f"\n{state['beschreibung']}")


if __name__ == "__main__":
    asyncio.run(main())
