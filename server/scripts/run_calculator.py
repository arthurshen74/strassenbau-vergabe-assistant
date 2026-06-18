"""Run the EKT calculator agent on a real LV position from the command line.

A thin harness over shared/services/calculator: it loads one LV position from the
project's LV document, wires the agent's retrieval seam to RetrievalService (so the
LLM sites can search the tender documents), runs the LangGraph app, and walks the
two HITL interrupts interactively (classification gate, batched EKT review). The
whole run is traced to Phoenix (docker-compose `phoenix`, UI on :6006).

    python -m scripts.run_calculator --project <uuid> --oz 01.03.0004

--mock answers the three LLM sites with canned replies (wired to the FSS demo
position) and skips retrieval; the rest of the pipeline runs unchanged. The model
behind the live sites is settings.calculator_model (CALCULATOR_MODEL in .env).
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
    REASONING_LLM,
    REASONING_NARRATION,
    STAGE_CLASSIFICATION,
    STAGE_DRIVER_CONFIRMATION,
    build_graph,
)
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.retrieval import RetrievalService

PHOENIX_PROJECT = "ekt-calculator"

# Provider reasoning summaries can run long; the full text stays in state/Phoenix.
PROVIDER_REASONING_PREVIEW = 400


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the EKT calculator agent on one LV position."
    )
    parser.add_argument("--project", type=UUID, required=True, help="project_uuid")
    parser.add_argument("--oz", required=True, help="Ordnungszahl, e.g. 01.03.0004")
    parser.add_argument(
        "--mock", action="store_true",
        help="canned LLM replies (FSS demo) and no retrieval; pipeline runs unchanged",
    )
    parser.add_argument("--no-trace", action="store_true", help="skip Phoenix tracing")
    return parser.parse_args()


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
            print(f"no LV position {args.oz} in project {args.project}", file=sys.stderr)
            raise SystemExit(1)

        config = CALCULATOR_RETRIEVAL_CONFIG

        async def retrieve(query: str) -> list[str]:
            ctx = await retrieval.retrieve_context(query, args.project, config)
            return [c.chunk_text for c in ctx.context]

        prompts: dict = {}
        if not args.mock:
            async with engine.connect() as conn:
                prompts = await load_calculator_prompts(conn)
        app = build_graph(
            retriever=None if args.mock else retrieve, llm=llm, prompts=prompts
        )
        cfg = {"configurable": {"thread_id": f"ekt-{args.project}-{args.oz}"}}

        print(f"position {item.oz}: {item.kurztext} — {item.menge} {item.einheit}")
        pending = await _stream(app, cfg,
                                {"position": _position(item), "project_uuid": args.project})
        while pending is not None:
            command = await _prompt_for_resume(app, cfg, pending)
            pending = await _stream(app, cfg, command)

        state = (await app.aget_state(cfg)).values
        _print_state(state)
        if "form_223" in state:
            _print_form_223(state["form_223"])
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
        "boq_menge": float(item.menge),
        "boq_einheit": item.einheit,
    }


async def _stream(app: Any, cfg: dict, payload: Any) -> dict | None:
    """Run until the next interrupt or completion, printing reasoning live.

    Returns the interrupt payload to resume from, or None when the run ends."""
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
    else:                                       # provider reasoning summary
        text = " ".join(entry["text"].split())
        if len(text) > PROVIDER_REASONING_PREVIEW:
            text = text[:PROVIDER_REASONING_PREVIEW].rstrip() + "..."
        print(f"    (model reasoning) {text}")


async def _prompt_for_resume(app: Any, cfg: dict, payload: dict) -> Command:
    if payload.get("stage") == STAGE_CLASSIFICATION:
        print("\nGRAPH PAUSED: classification gate")
        print(f"  suggestion : {payload['agent_suggestion']} "
              f"@ {payload['confidence']:.2f}")
        print(f"  notes      : {payload['notes']}")
        print(f"  options    : {', '.join(payload['options'])}")
        answer = await _prompt(f"work_type [{payload['agent_suggestion']}]> ")
        choice = answer or payload["agent_suggestion"]
        return Command(resume={"work_type": choice})

    if payload.get("stage") == STAGE_DRIVER_CONFIRMATION:
        print("\nGRAPH PAUSED: driver confirmation (assumed drivers)")
        overrides: dict[str, str] = {}
        for d in payload["confirm"]:
            conf = f"{d['confidence']:.2f}" if d["confidence"] is not None else "n/a"
            print(f"\n  {d['id']} = {d['value']} {d['einheit'] or ''}  "
                  f"(confidence {conf})")
            if d["description"]:
                print(f"    rule   : {d['description']}")
            if d["source"]:
                print(f"    source : {d['source']}")
            answer = await _prompt(
                f"  {d['id']} [enter = accept {d['value']}]> ")
            if answer:
                overrides[d["id"]] = answer
        return Command(resume={"drivers": overrides})

    print("\nGRAPH PAUSED: hitl_review interrupt (Kalkulator's batched review)")
    _print_state((await app.aget_state(cfg)).values)
    print(f"\n  actions: {', '.join(payload['actions'])}")
    action = await _prompt("action [approve]> ") or "approve"
    return Command(resume={"action": action})


async def _prompt(label: str) -> str:
    return (await asyncio.to_thread(input, label)).strip()


def _print_state(state: dict) -> None:
    print(f"\nClassification: {state['work_type']} "
          f"@ {state['classification_confidence']:.2f}")
    print(f"  {state['classification_notes']}")
    print("\nDrivers:")
    for k, v in state["drivers"].items():
        p = state["driver_provenance"].get(k, {})
        print(f"  {k:18} = {v}   ({p.get('confidence', 1.0):.2f})")
    print("\nOperations:")
    for r in state["operation_results"]:
        m = f" / {r['method']} @ {r['method_confidence']:.2f}" if r["method"] else ""
        print(f"  {r['operation']}{m}  ->  {r['eur_total']:>9.2f} EUR")
        for line in r["lines"]:
            val = (f"{line['out_value']} {line['out_einheit']}" if line["out_id"]
                   else f"{line['eur']:.2f} EUR")
            note = f"   [{line['note']}]" if line.get("note") else ""
            print(f"      - {line['goal'][:58]:58} {val}{note}")
    e = state["ekt"]
    print(f"\nEKT: {e['total_eur']} EUR total -> {e['per_unit_eur']} EUR/"
          f"{e['einheit']}  (registry v{e['registry_version']})")
    print("\nReview flags (batched for the Kalkulator):")
    for f in state["review_flags"]:
        print(f"  [{f['kind']:14}] {f['where']:22} {f['detail'][:90]}")


def _print_form_223(row: dict) -> None:
    me = row["mengeneinheit"]
    print("\nVHB 223 — Aufgliederung der Einheitspreise (ohne Umsatzsteuer):")
    print(f"  OZ des LV     : {row['oz']}")
    print(f"  Teilleistung  : {row['kurzbezeichnung']}")
    print(f"  Menge         : {row['menge']} {me}")
    print(f"  Zeitansatz    : {row['zeitansatz_h']} h/{me}")
    print(f"  Lohn          : {row['lohn_eur']} EUR/{me}")
    print(f"  Stoffe        : {row['stoffe_eur']} EUR/{me}")
    print(f"  Geräte        : {row['geraete_eur']} EUR/{me}")
    print(f"  Sonstiges     : {row['sonstiges_eur']} EUR/{me}")


if __name__ == "__main__":
    asyncio.run(main())
