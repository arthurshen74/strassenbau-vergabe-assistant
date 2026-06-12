"""LangGraph wiring for the EKT Position Calculation Agent.

Topology (matches the state diagram):
  classify -> [confidence gate -> hitl_classify?] -> resolve_drivers
  -> derive_drivers (cross-operation dependencies computed ONCE, e.g. tonnage)
  -> plan_operations --Send x N (parallel)--> cost_operation (registry interpreter)
  -> aggregate_etk -> assess_risk -> hitl_review (interrupt) -> route_feedback

Determinism contract:
  - LLM writes ONLY judgment fields (work_type, driver decisions, method).
  - Numbers exist ONLY as formula outputs / store reads, each with provenance.
  - Low-confidence judgments do NOT pause the fan-out; they append to
    review_flags (reducer-merged) and surface at the single batched review.
"""
from __future__ import annotations
import operator
from pathlib import Path
from typing import Annotated, Optional, TypedDict

import yaml
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

import llm_calls
from formulas import FORMULAS
from models import (CostLine, OperationDef, OperationResult, Registry,
                    ResolvedParam, ReviewFlag)
from stores import STORES, climate, fleet_availability

REGISTRY_DIR = Path(__file__).parent / "registry"
CONFIDENCE_GATE = 0.7          # classification below this -> HITL interrupt
FLAG_THRESHOLD = 0.8           # judgments below this -> batched review flag


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
    work_type: str
    classification_notes: str
    classification_confidence: float
    drivers: dict                      # resolved + derived, value-by-id
    driver_provenance: dict            # id -> {source, quote, confidence}
    operation_results: Annotated[list[dict], operator.add]   # reducer (Send fan-in)
    review_flags: Annotated[list[dict], operator.add]        # reducer (Send fan-in)
    ekt: dict
    decision: dict                     # review outcome


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
                    note=result.get("note"))
    if row.out:                                        # intermediate value (hours, t)
        priors[row.out.id] = result["value"]
        line.out_id, line.out_value, line.out_einheit = (
            row.out.id, result["value"], row.out.einheit)
    return line


# ------------------------------------------------------------------- nodes --
def classify(state: AgentState) -> dict:
    index = [{"work_type": r.work_type, "keywords": r.triggers.get("keywords", [])}
             for r in REGISTRIES.values()]
    res = llm_calls.classify_position(state["position"], index)
    return {"work_type": res.work_type,
            "classification_confidence": res.confidence,
            "classification_notes": res.notes}


def route_after_classify(state: AgentState) -> str:
    ok = (state["work_type"] in REGISTRIES
          and state["classification_confidence"] >= CONFIDENCE_GATE)
    return "resolve_drivers" if ok else "hitl_classify"


def hitl_classify(state: AgentState) -> dict:
    answer = interrupt({
        "stage": "classification",
        "agent_suggestion": state["work_type"],
        "confidence": state["classification_confidence"],
        "notes": state["classification_notes"],
        "options": list(REGISTRIES) + ["CANCEL"],
    })
    return {"work_type": answer["work_type"], "classification_confidence": 1.0,
            "classification_notes": "set by Kalkulator (HITL)"}


def route_after_hitl(state: AgentState) -> str:
    return END if state["work_type"] == "CANCEL" else "resolve_drivers"


def resolve_drivers(state: AgentState) -> dict:
    reg = REGISTRIES[state["work_type"]]
    specs = [d.model_dump() for d in reg.drivers]
    # tool-sourced drivers are fetched deterministically, not asked of the LLM
    tool_values = {d.id: climate()["ambient_temp_c"]
                   for d in reg.drivers if d.source == "tool:climate"}
    res = llm_calls.resolve_drivers(specs, state["position"])
    drivers, prov, flags = dict(tool_values), {}, []
    for dv in res.drivers:
        if dv.id in tool_values:
            prov[dv.id] = {"source": "tool:climate", "confidence": 1.0}
            continue
        drivers[dv.id] = dv.value
        prov[dv.id] = {"source": dv.source_quote or "judgment",
                       "confidence": dv.confidence}
        if dv.value is None:
            flags.append(ReviewFlag(where=f"driver:{dv.id}", kind="missing_data",
                                    detail="not found in documents").model_dump())
        elif dv.confidence < FLAG_THRESHOLD:
            flags.append(ReviewFlag(where=f"driver:{dv.id}", kind="low_confidence",
                                    detail=f"{dv.value} @ {dv.confidence:.2f}").model_dump())
    for note in res.flags:
        flags.append(ReviewFlag(where="drivers", kind="low_confidence",
                                detail=note).model_dump())
    return {"drivers": drivers, "driver_provenance": prov, "review_flags": flags}


def derive_drivers(state: AgentState) -> dict:
    """Cross-operation dependencies (tonnage etc.) computed ONCE before fan-out."""
    reg = REGISTRIES[state["work_type"]]
    drivers = dict(state["drivers"])
    for dd in reg.derived_drivers:
        schema, fn = FORMULAS[dd.formula]
        kwargs, _ = resolve_params(dd.params, drivers, {}, {})
        drivers[dd.id] = fn(schema(**kwargs))["value"]
    return {"drivers": drivers}


def plan_operations(state: AgentState) -> dict:
    return {}                                   # fan-out happens on the edge


def fan_out(state: AgentState):
    reg = REGISTRIES[state["work_type"]]
    return [Send("cost_operation",
                 {"op_def": op.model_dump(by_alias=True),
                  "drivers": state["drivers"]})
            for op in reg.operations]


def cost_operation(payload: dict) -> dict:
    """Registry interpreter for ONE operation - one parallel Send branch.

    No interrupts in here: low confidence / blocked rows append review_flags
    and the run continues (optimistic execution, batched review).
    """
    op = OperationDef.model_validate(payload["op_def"])
    drivers = payload["drivers"]
    flags: list[dict] = []
    method_id, m_conf, m_notes = None, None, None
    ctx = {"operation_id": op.id, "access_class": drivers.get("access_class")}

    if op.methods:                                       # LLM site 3 (judgment)
        rel = {k: drivers.get(k) for k in (op.selection.on if op.selection else [])}
        sel = llm_calls.select_method(
            {"id": op.id, "label": op.label,
             "methods": [m.model_dump() for m in op.methods]},
            rel, fleet_availability(), notes=[])
        if sel.method == "escalate":
            flags.append(ReviewFlag(where=f"operation:{op.id}", kind="blocked",
                                    detail=sel.notes).model_dump())
            return {"operation_results": [OperationResult(
                        operation=op.id, method=None, lines=[], eur_total=0.0
                    ).model_dump()],
                    "review_flags": flags}
        method_id, m_conf, m_notes = sel.method, sel.confidence, sel.notes
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
            "review_flags": flags}


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
        "stage": "ekt_review",
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
    return {}


# ------------------------------------------------------------------- build --
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("hitl_classify", hitl_classify)
    g.add_node("resolve_drivers", resolve_drivers)
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
    g.add_edge("resolve_drivers", "derive_drivers")
    g.add_edge("derive_drivers", "plan_operations")
    g.add_conditional_edges("plan_operations", fan_out, ["cost_operation"])
    g.add_edge("cost_operation", "aggregate_etk")     # automatic fan-in (join)
    g.add_edge("aggregate_etk", "assess_risk")
    g.add_edge("assess_risk", "hitl_review")
    g.add_edge("hitl_review", "route_feedback")
    g.add_edge("route_feedback", END)
    return g.compile(checkpointer=MemorySaver())
