"""LangGraph wiring for the EKT Position Calculation Agent.

Topology (matches the state diagram):
  classify -> [confidence gate -> hitl_classify?] -> resolve_drivers
  -> hitl_confirm_drivers (interrupt iff the registry marks confirm: drivers)
  -> derive_drivers (cross-operation dependencies computed ONCE, e.g. tonnage)
  -> plan_operations --Send x N (parallel)--> cost_operation (registry interpreter)
  -> aggregate_etk -> assess_risk -> hitl_review (interrupt) -> route_feedback

Determinism contract:
  - LLM writes ONLY judgment fields (work_type, driver decisions, method).
  - Numbers exist ONLY as formula outputs / store reads, each with provenance.
  - Low-confidence judgments do NOT pause the fan-out; they append to
    review_flags (reducer-merged) and surface at the single batched review.

RAG seam: `build_graph` takes an async `query -> evidence snippets` retriever.
The three LLM sites query it before judging: classification retrieves project
context around the position, driver resolution retrieves per-driver context
(query = the driver's German `hint` + Kurztext, for plan/project drivers), and
method selection retrieves context per operation. With retriever=None the
graph runs document-blind (mock/offline).
"""

from __future__ import annotations

import logging
import operator
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, TypedDict
from uuid import UUID

import yaml
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from shared.clients.llm.client import LLMClient
from shared.models.enums import RetrievalModality
from shared.services.calculator import llm_calls
from shared.services.calculator.form223 import build_form_223_row
from shared.services.calculator.formulas import FORMULAS
from shared.services.calculator.models import (
    CostLine,
    OperationDef,
    OperationResult,
    Registry,
    ResolvedParam,
    ReviewFlag,
)
from shared.services.calculator.stores import STORES, climate, fleet_availability
from shared.services.retrieval.config import RetrievalConfig

REGISTRY_DIR = Path(__file__).parent / "registry"
CONFIDENCE_GATE = 0.7          # classification below this -> HITL interrupt
FLAG_THRESHOLD = 0.8           # judgments below this -> batched review flag

# Async `query -> formatted evidence snippets` callable; None runs without retrieval.
ContextRetriever = Callable[[str], Awaitable[list[str]]]

# Driver source discriminators (registry YAML <-> graph). lv_text reads the LV position; tool:*
# drivers are fetched deterministically; everything else (plan/project/judgment) is resolved from
# retrieved tender-document context only.
DRIVER_SOURCE_LV_TEXT = "lv_text"
DRIVER_SOURCE_TOOL_PREFIX = "tool:"
DRIVER_SOURCE_CLIMATE = "tool:climate"

# The calculator's retrieval policy: hybrid dense + BM25 fused by RRF, multi-question expansion,
# cross-encoder rerank, PLUS scope (project documents + the LV). Shared by every entry point so the
# CLI and the conversation-backed service resolve drivers against the same evidence.
CALCULATOR_RETRIEVAL_CONFIG = RetrievalConfig(
    modality=RetrievalModality.PLUS,
    multi_query=True,
    use_bm25=True,
    use_cross_encoder=True,
)

# Interrupt payload stages; the CLI dispatches its prompts on these.
STAGE_CLASSIFICATION = "classification"
STAGE_DRIVER_CONFIRMATION = "driver_confirmation"
STAGE_EKT_REVIEW = "ekt_review"

PROVENANCE_HITL = "set by Kalkulator (HITL)"

# reasoning_log entry kinds: deterministic stage narration, the LLM's structured
# reasoning steps, and the provider's raw reasoning summary (best-effort).
REASONING_NARRATION = "narration"
REASONING_LLM = "llm"
REASONING_PROVIDER = "provider"


logger = logging.getLogger(__name__)

# Diagnostic: the writer being unavailable under a streaming run means live reasoning is silently
# dropped (the "stuck, then a burst" symptom). Expected to be absent only for CLI / ainvoke, so we
# warn once per process rather than per entry.
_writer_unavailable_warned = False


def _write_live(entry: dict) -> None:
    """Emit one reasoning entry to the custom stream so the UI and logs see it the moment it is
    created, mid-node. The sequential driver loop is a single graph node, so without this its
    per-driver progress would be buffered until the whole node returns (stream_mode='updates' only
    yields per node). No-op when the run isn't streaming with custom mode (CLI / ainvoke)."""
    global _writer_unavailable_warned
    try:
        writer = get_stream_writer()
    except RuntimeError:
        if not _writer_unavailable_warned:
            logger.warning(
                "calculator stream writer unavailable (get_stream_writer raised); live reasoning "
                "deltas will not stream. Expected only for CLI/ainvoke, not an SSE run."
            )
            _writer_unavailable_warned = True
        return
    writer(entry)


def reason(stage: str, kind: str, text: str) -> dict:
    entry = {"stage": stage, "kind": kind, "text": text}
    _write_live(entry)
    return entry


def reason_llm(stage: str, steps: list[str], provider: str | None) -> list[dict]:
    """The reasoning_log entries for one LLM call: structured steps + summary."""
    entries = [reason(stage, REASONING_LLM, step) for step in steps]
    if provider:
        entries.append(reason(stage, REASONING_PROVIDER, provider))
    return entries

# Driver einheiten that are NOT numeric; everything else is coerced to float after
# resolution (judgment drivers have einheit None and are never coerced).
NON_NUMERIC_EINHEITEN = (None, "text")

# First numeric token in a verbatim document read, e.g. "ca. 0,30" or ">= 50,0 cm".
# German thousands separators ("12.500") are not handled; driver values are small.
NUMERIC_TOKEN_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def coerce_numeric(value: object) -> float | None:
    """Deterministically parse a resolved driver value to float, or None.

    The LLM copies document values verbatim (convert nothing); this is the
    deterministic normalization between that read and the formula schemas."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = NUMERIC_TOKEN_RE.search(value)
        if match:
            return float(match.group().replace(",", "."))
    return None


def load_registries() -> dict[str, Registry]:
    regs = {}
    for f in REGISTRY_DIR.glob("*.yaml"):
        reg = Registry.model_validate(yaml.safe_load(f.read_text()))
        regs[reg.work_type] = reg
    return regs

REGISTRIES = load_registries()


# ------------------------------------------------------------------- state --
class AgentState(TypedDict, total=False):
    position: dict                     # the LV position + context docs
    project_uuid: UUID                 # attribution for usage / execution-log telemetry
    conversation_uuid: UUID            # set when driven from the chat UI (None in the CLI)
    work_type: str
    classification_notes: str
    classification_confidence: float
    drivers: dict                      # resolved + derived, value-by-id
    driver_provenance: dict            # id -> {source, quote, confidence}
    operation_results: Annotated[list[dict], operator.add]   # reducer (Send fan-in)
    review_flags: Annotated[list[dict], operator.add]        # reducer (Send fan-in)
    reasoning_log: Annotated[list[dict], operator.add]       # narration + LLM reasoning
    ekt: dict
    decision: dict                     # review outcome
    form_223: dict                     # EP-Aufgliederung, set on approve


# ----------------------------------------------------- param resolution -----
def resolve_params(rows_params, drivers, ctx, priors):
    """Turn a registry row's ParamSpecs into validated formula kwargs + provenance."""
    kwargs, prov = {}, {}
    for name, spec in rows_params.items():
        if spec.from_ == "drivers":
            kwargs[name] = drivers[spec.field]
            prov[name] = ResolvedParam(value=kwargs[name], source=f"driver:{spec.field}")
        elif spec.from_ == "store":
            args = [ctx.get(a, drivers.get(a)) for a in spec.args] + spec.args_const
            kwargs[name] = STORES[spec.call](*args)
            prov[name] = ResolvedParam(value=kwargs[name],
                                       source=f"store:{spec.call}({', '.join(map(str, args))})")
        elif spec.from_ == "prior":
            kwargs[name] = priors[spec.ref]
            prov[name] = ResolvedParam(value=kwargs[name], source=f"prior:{spec.ref}")
        elif spec.from_ == "const":
            kwargs[name] = spec.value
            prov[name] = ResolvedParam(value=spec.value, source="const")
    return kwargs, prov


def run_row(row, drivers, ctx, priors, operation_id, method_id):
    schema, fn = FORMULAS[row.formula]
    kwargs, prov = resolve_params(row.params, drivers, ctx, priors)
    result = fn(schema(**kwargs))                      # Pydantic gate -> pure function
    line = CostLine(operation=operation_id, method=method_id, goal=row.goal,
                    formula=row.formula, params=prov, eur=result.get("eur"),
                    labor_h=result.get("labor_h"), note=result.get("note"))
    if row.out:                                        # intermediate value (hours, t)
        priors[row.out.id] = result["value"]
        line.out_id, line.out_value, line.out_einheit = (
            row.out.id, result["value"], row.out.einheit)
    return line


# ------------------------------------------------- deterministic nodes ------
def route_after_classify(state: AgentState) -> str:
    ok = (state["work_type"] in REGISTRIES
          and state["classification_confidence"] >= CONFIDENCE_GATE)
    return "resolve_drivers" if ok else "hitl_classify"


def hitl_classify(state: AgentState) -> dict:
    answer = interrupt({
        "stage": STAGE_CLASSIFICATION,
        "agent_suggestion": state["work_type"],
        "confidence": state["classification_confidence"],
        "notes": state["classification_notes"],
        "options": list(REGISTRIES) + ["CANCEL"],
    })
    return {"work_type": answer["work_type"], "classification_confidence": 1.0,
            "classification_notes": PROVENANCE_HITL}


def route_after_hitl(state: AgentState) -> str:
    return END if state["work_type"] == "CANCEL" else "resolve_drivers"


def hitl_confirm_drivers(state: AgentState) -> dict:
    """Pause for the Kalkulator to bless assumption-based drivers (confirm: true).

    The registry marks drivers whose resolution rests on an assumption (e.g.
    strip_length_m read from the Baubeschreibung's Ausbaulaenge). The reviewer
    confirms each value or types a correction; corrections get HITL provenance
    and full confidence. No confirm-drivers in the registry -> no pause."""
    reg = REGISTRIES[state["work_type"]]
    to_confirm = [d for d in reg.drivers if d.confirm]
    if not to_confirm:
        return {}
    prov = state["driver_provenance"]
    answer = interrupt({
        "stage": STAGE_DRIVER_CONFIRMATION,
        "confirm": [{
            "id": d.id,
            "einheit": d.einheit,
            "description": d.description,
            "value": state["drivers"].get(d.id),
            "source": prov.get(d.id, {}).get("source"),
            "confidence": prov.get(d.id, {}).get("confidence"),
        } for d in to_confirm],
        "drivers": state["drivers"],
        "review_flags": state.get("review_flags", []),
    })
    overrides = answer.get("drivers", {})
    if not overrides:
        return {"reasoning_log": [reason("hitl_confirm_drivers", REASONING_NARRATION,
                                         "Kalkulator accepted the assumed drivers as-is.")]}
    einheit_by_id = {d.id: d.einheit for d in reg.drivers}
    drivers, new_prov = dict(state["drivers"]), dict(prov)
    log = []
    for driver_id, raw in overrides.items():
        value = raw
        if einheit_by_id.get(driver_id) not in NON_NUMERIC_EINHEITEN:
            value = coerce_numeric(raw)
        drivers[driver_id] = value
        new_prov[driver_id] = {"source": PROVENANCE_HITL, "confidence": 1.0}
        log.append(reason("hitl_confirm_drivers", REASONING_NARRATION,
                          f"Kalkulator set {driver_id} = {value}."))
    return {"drivers": drivers, "driver_provenance": new_prov, "reasoning_log": log}


def derive_drivers(state: AgentState) -> dict:
    """Cross-operation dependencies (tonnage etc.) computed ONCE before fan-out.

    Fails soft like the fan-out: a derived driver whose inputs are missing or
    unparseable becomes a review flag, and the rows depending on it flag
    themselves downstream (optimistic execution, batched review)."""
    reg = REGISTRIES[state["work_type"]]
    drivers = dict(state["drivers"])
    flags: list[dict] = []
    log: list[dict] = []
    for dd in reg.derived_drivers:
        schema, fn = FORMULAS[dd.formula]
        try:
            kwargs, _ = resolve_params(dd.params, drivers, {}, {})
            drivers[dd.id] = fn(schema(**kwargs))["value"]
            log.append(reason("derive_drivers", REASONING_NARRATION,
                              f"Derived {dd.id} = {drivers[dd.id]} {dd.einheit} "
                              f"({dd.formula})."))
        except Exception as exc:
            flags.append(ReviewFlag(where=f"derived:{dd.id}", kind="blocked",
                                    detail=" ".join(str(exc).split())).model_dump())
            log.append(reason("derive_drivers", REASONING_NARRATION,
                              f"Could not derive {dd.id}; flagged for review."))
    return {"drivers": drivers, "review_flags": flags, "reasoning_log": log}


def plan_operations(state: AgentState) -> dict:
    reg = REGISTRIES[state["work_type"]]        # fan-out happens on the edge
    ops = ", ".join(op.id for op in reg.operations)
    return {"reasoning_log": [
        reason("plan_operations", REASONING_NARRATION, "I need to plan the operations."),
        reason("plan_operations", REASONING_NARRATION,
               f"Registry {reg.work_type} v{reg.version} defines "
               f"{len(reg.operations)} operations: {ops}. Costing them in parallel."),
    ]}


def fan_out(state: AgentState):
    reg = REGISTRIES[state["work_type"]]
    return [Send("cost_operation",
                 {"op_def": op.model_dump(by_alias=True),
                  "drivers": state["drivers"],
                  "kurztext": state["position"]["kurztext"],
                  "project_uuid": state.get("project_uuid"),
                  "conversation_uuid": state.get("conversation_uuid")})
            for op in reg.operations]


def aggregate_etk(state: AgentState) -> dict:
    menge = state["position"]["boq_menge"]
    total = round(sum(r["eur_total"] for r in state["operation_results"]), 2)
    return {"ekt": {
        "total_eur": total,
        "per_unit_eur": round(total / menge, 2),
        "einheit": state["position"]["boq_einheit"],
        "by_operation": {r["operation"]: r["eur_total"]
                         for r in state["operation_results"]},
        "registry_version": REGISTRIES[state["work_type"]].version,
    }}


def assess_risk(state: AgentState) -> dict:
    flags = []
    if "Auftragsprofil" in state["position"].get("langtext", ""):
        flags.append(ReviewFlag(
            where="position", kind="risk",
            detail="Billed by Auftragsprofil in nichttragfaehige Teilflaechen: "
                   "quantity unknown until milling -> §2(3) VOB/B exposure. "
                   "Route to Wagnis, not EKT.").model_dump())
    return {"review_flags": flags}


def hitl_review(state: AgentState) -> dict:
    decision = interrupt({                       # graph pauses; Kalkulator reviews
        "stage": STAGE_EKT_REVIEW,
        "ekt": state["ekt"],
        "review_flags": state["review_flags"],
        "operations": [{k: r[k] for k in
                        ("operation", "method", "method_confidence", "eur_total")}
                       for r in state["operation_results"]],
        "actions": ["approve", "edit_value", "recost_operation", "reject"],
    })
    return {"decision": decision}


def route_feedback(state: AgentState) -> dict:
    # Stub of the feedback router: numbers -> stores, judgment -> ReasoningNotes.
    d = state["decision"]
    print(f"\n[route_feedback] action={d.get('action')} "
          f"-> numeric corrections to stores, prose rationale to ReasoningNotes")
    if d.get("action") != "approve":
        return {}
    row = build_form_223_row(state["position"], state["operation_results"])
    return {"form_223": row.model_dump()}


# ------------------------------------------------------------------- build --
def build_graph(
    retriever: ContextRetriever | None = None,
    llm: LLMClient | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the agent graph. The LLM-judging nodes close over `retriever` and `llm`.

    `llm` is the shared transport the three judging sites call through (telemetry +
    provider-reasoning capture); it is unused in mock mode, so it may be None there.
    `checkpointer` persists graph state across the HITL interrupts; defaults to an in-process
    MemorySaver (the conversation-backed service injects an AsyncPostgresSaver)."""

    async def retrieve(query: str) -> list[str]:
        return await retriever(query) if retriever is not None else []

    async def classify(state: AgentState) -> dict:
        index = [{"work_type": r.work_type, "keywords": r.triggers.get("keywords", [])}
                 for r in REGISTRIES.values()]
        snippets = await retrieve(state["position"]["kurztext"])
        res, provider = await llm_calls.classify_position(
            llm, state["position"], index, snippets,
            project_uuid=state.get("project_uuid"),
            conversation_uuid=state.get("conversation_uuid"))
        log = [reason("classify", REASONING_NARRATION,
                      "I need to assign the position to a Leistung.")]
        log += reason_llm("classify", res.reasoning, provider)
        log.append(reason("classify", REASONING_NARRATION,
                          f"Assigned {res.work_type} @ {res.confidence:.2f}: {res.notes}"))
        return {"work_type": res.work_type,
                "classification_confidence": res.confidence,
                "classification_notes": res.notes,
                "reasoning_log": log}

    async def resolve_drivers(state: AgentState) -> dict:
        """Resolve each driver in turn: gather its evidence, ask the LLM for ONE decision,
        record value + provenance + reasoning. Sequential (not batched) so a human can follow
        the chain and later drivers can lean on the ones resolved before them."""
        reg = REGISTRIES[state["work_type"]]
        position = state["position"]
        kurztext = position["kurztext"]
        project_uuid = state.get("project_uuid")
        conversation_uuid = state.get("conversation_uuid")
        einheit_by_id = {d.id: d.einheit for d in reg.drivers}

        # tool-sourced drivers are fetched deterministically and never asked of the LLM.
        drivers = {d.id: climate()["ambient_temp_c"]
                   for d in reg.drivers if d.source == DRIVER_SOURCE_CLIMATE}
        prov = {d_id: {"source": DRIVER_SOURCE_CLIMATE, "confidence": 1.0} for d_id in drivers}
        to_resolve = [d for d in reg.drivers
                      if not d.source.startswith(DRIVER_SOURCE_TOOL_PREFIX)]
        flags: list[dict] = []
        log = [reason("resolve_drivers", REASONING_NARRATION,
                      f"I need to resolve {len(to_resolve)} drivers, one at a time: "
                      f"{', '.join(d.id for d in to_resolve)}.")]

        for d in to_resolve:
            if d.source == DRIVER_SOURCE_LV_TEXT:
                evidence = {"lv_position": {"kurztext": kurztext,
                                            "langtext": position.get("langtext")}}
                log.append(reason("resolve_drivers", REASONING_NARRATION,
                                  f"Resolving {d.id} ({d.source}) from the LV position text."))
            else:                                   # plan / project / judgment: retrieved only
                snippets = await retrieve(f"{d.hint or d.id} - {kurztext}")
                evidence = {"retrieved_context": snippets}
                log.append(reason("resolve_drivers", REASONING_NARRATION,
                                  f"Resolving {d.id} ({d.source}); retrieved "
                                  f"{len(snippets)} document snippet(s)."))

            decision, provider = await llm_calls.resolve_one_driver(
                llm, d.model_dump(), evidence, drivers,
                project_uuid=project_uuid, conversation_uuid=conversation_uuid)
            log += reason_llm("resolve_drivers", decision.reasoning, provider)

            einheit = einheit_by_id.get(d.id)
            value = decision.value
            if value is not None and einheit not in NON_NUMERIC_EINHEITEN:
                value = coerce_numeric(value)
            drivers[d.id] = value
            prov[d.id] = {"source": decision.source_quote or "judgment",
                          "confidence": decision.confidence,
                          "reasoning": decision.reasoning}

            if decision.value is None:
                flags.append(ReviewFlag(where=f"driver:{d.id}", kind="missing_data",
                                        detail=decision.note or "not found in documents"
                                        ).model_dump())
                log.append(reason("resolve_drivers", REASONING_NARRATION,
                                  f"{d.id}: not found -> flagged "
                                  f"({decision.note or 'no value'})."))
            elif value is None:
                flags.append(ReviewFlag(where=f"driver:{d.id}", kind="missing_data",
                                        detail=f"non-numeric value {decision.value!r} "
                                               f"(einheit {einheit})").model_dump())
                log.append(reason("resolve_drivers", REASONING_NARRATION,
                                  f"{d.id}: non-numeric value {decision.value!r} -> flagged."))
            else:
                if decision.confidence < FLAG_THRESHOLD:
                    flags.append(ReviewFlag(where=f"driver:{d.id}", kind="low_confidence",
                                            detail=f"{value} @ {decision.confidence:.2f}"
                                            ).model_dump())
                log.append(reason("resolve_drivers", REASONING_NARRATION,
                                  f"{d.id} = {value} {einheit or ''} @ "
                                  f"{decision.confidence:.2f}."))

        log.append(reason("resolve_drivers", REASONING_NARRATION,
                          f"Resolved {len(drivers)} drivers, {len(flags)} flagged for review."))
        return {"drivers": drivers, "driver_provenance": prov,
                "review_flags": flags, "reasoning_log": log}

    async def cost_operation(payload: dict) -> dict:
        """Registry interpreter for ONE operation - one parallel Send branch.

        No interrupts in here: low confidence / blocked rows append review_flags
        and the run continues (optimistic execution, batched review).
        """
        op = OperationDef.model_validate(payload["op_def"])
        drivers = payload["drivers"]
        stage = f"operation:{op.id}"
        flags: list[dict] = []
        log: list[dict] = []
        method_id, m_conf, m_notes = None, None, None
        ctx = {"operation_id": op.id, "access_class": drivers.get("access_class")}

        if op.methods:                                       # LLM site 3 (judgment)
            rel = {k: drivers.get(k) for k in (op.selection.on if op.selection else [])}
            notes = await retrieve(f"{op.label} Bauweise - {payload['kurztext']}")
            log.append(reason(stage, REASONING_NARRATION,
                              f"I need to choose the Bauweise for '{op.label}'."))
            sel, provider = await llm_calls.select_method(
                llm,
                {"id": op.id, "label": op.label,
                 "methods": [m.model_dump() for m in op.methods]},
                rel, fleet_availability(), notes=notes,
                project_uuid=payload.get("project_uuid"),
                conversation_uuid=payload.get("conversation_uuid"))
            log += reason_llm(stage, sel.reasoning, provider)
            if sel.method == "escalate":
                flags.append(ReviewFlag(where=f"operation:{op.id}", kind="blocked",
                                        detail=sel.notes).model_dump())
                log.append(reason(stage, REASONING_NARRATION,
                                  f"No method fits '{op.label}'; escalating to review."))
                return {"operation_results": [OperationResult(
                            operation=op.id, method=None, lines=[], eur_total=0.0
                        ).model_dump()],
                        "review_flags": flags,
                        "reasoning_log": log}
            method_id, m_conf, m_notes = sel.method, sel.confidence, sel.notes
            log.append(reason(stage, REASONING_NARRATION,
                              f"Selected {method_id} @ {m_conf:.2f} for '{op.label}'."))
            ctx["method_id"] = method_id
            ctx["machine_class"] = next(m.machine_class for m in op.methods
                                        if m.id == method_id)
            if m_conf < FLAG_THRESHOLD:
                flags.append(ReviewFlag(where=f"operation:{op.id}", kind="low_confidence",
                                        detail=f"method {method_id} @ {m_conf:.2f}: {m_notes}"
                                        ).model_dump())

        lines, priors = [], {}
        for row in op.requirements:                          # deterministic walk
            try:
                lines.append(run_row(row, drivers, ctx, priors, op.id, method_id))
            except Exception as exc:                         # fail soft -> review
                flags.append(ReviewFlag(where=f"{op.id}:{row.formula}", kind="blocked",
                                        detail=str(exc)).model_dump())

        total = round(sum(l.eur for l in lines if l.eur), 2)
        return {"operation_results": [OperationResult(
                    operation=op.id, method=method_id, method_confidence=m_conf,
                    method_notes=m_notes, lines=lines, eur_total=total).model_dump()],
                "review_flags": flags,
                "reasoning_log": log}

    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("hitl_classify", hitl_classify)
    g.add_node("resolve_drivers", resolve_drivers)
    g.add_node("hitl_confirm_drivers", hitl_confirm_drivers)
    g.add_node("derive_drivers", derive_drivers)
    g.add_node("plan_operations", plan_operations)
    g.add_node("cost_operation", cost_operation)
    g.add_node("aggregate_etk", aggregate_etk)
    g.add_node("assess_risk", assess_risk)
    g.add_node("hitl_review", hitl_review)
    g.add_node("route_feedback", route_feedback)

    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route_after_classify,
                            ["resolve_drivers", "hitl_classify"])
    g.add_conditional_edges("hitl_classify", route_after_hitl,
                            ["resolve_drivers", END])
    g.add_edge("resolve_drivers", "hitl_confirm_drivers")
    g.add_edge("hitl_confirm_drivers", "derive_drivers")
    g.add_edge("derive_drivers", "plan_operations")
    g.add_conditional_edges("plan_operations", fan_out, ["cost_operation"])
    g.add_edge("cost_operation", "aggregate_etk")     # automatic fan-in (join)
    g.add_edge("aggregate_etk", "assess_risk")
    g.add_edge("assess_risk", "hitl_review")
    g.add_edge("hitl_review", "route_feedback")
    g.add_edge("route_feedback", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
