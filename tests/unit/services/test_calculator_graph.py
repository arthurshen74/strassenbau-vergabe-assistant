"""Tests for the kalkulation_v2 position-calculation graph (mock mode).

Drive the full 9-node flow offline (`settings.calculator_mock`): both HITL gates
(method review, variable review) and the deterministic compute, on the L 101
fraesen slice. The compute path is checked against the proven engine golden, and
the Gate B tiering / override / fail-soft behaviour is asserted.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from shared.config import settings
from shared.services.calculator.graph import (
    REASONING_NARRATION,
    build_graph,
)
from shared.services.calculator.state import (
    STAGE_METHOD_REVIEW,
    STAGE_VARIABLE_REVIEW,
    STATUS_UEBERSCHRIEBEN,
    TIER_SURFACED,
)

POSITION = {
    "oz": "01.02.0006",
    "kurztext": "Asphaltbefestigung abfraesen, 3 bis 4,5 cm",
    "langtext": "Vorhandene Asphaltbefestigung abfraesen und entsorgen.",
    "menge": "7800",
    "einheit": "m2",
    "baustoff_code": None,
    "leistung_hint": "L_FRAESEN_3_45",
}
VORGABEN = {"tiefe_cm": "4", "fraesgut_klasse": "1"}

GOLDEN_EP = "1.71"
GOLDEN_GP = "13347.36"


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setattr(settings, "calculator_mock", True)


def _payload(vorgaben=VORGABEN):
    return {"position": dict(POSITION), "vorgaben": dict(vorgaben)}


async def _to_gate_b(app, cfg, vorgaben=VORGABEN):
    """Start a run and step through Gate A, returning the Gate B interrupt payload."""
    result = await app.ainvoke(_payload(vorgaben), cfg)
    assert result["__interrupt__"][0].value["stage"] == STAGE_METHOD_REVIEW
    result = await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg)
    return result["__interrupt__"][0].value


async def test_method_review_is_gate_a():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "ga"}}
    result = await app.ainvoke(_payload(), cfg)
    gate = result["__interrupt__"][0].value
    assert gate["stage"] == STAGE_METHOD_REVIEW
    assert gate["leistung_key"] == "L_FRAESEN_3_45"
    assert gate["bauverfahren_kandidaten"] == ["BV_FRAESEN"]
    assert gate["bauverfahren_default"] == "BV_FRAESEN"


async def test_variable_review_tiers_high_stakes_surfaced():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "gb"}}
    gate = await _to_gate_b(app, cfg)

    assert gate["stage"] == STAGE_VARIABLE_REVIEW
    surfaced = {v["name"] for v in gate["surfaced"]}
    collapsed = {v["name"] for v in gate["collapsed"]}
    # Only the two high-stakes (no-default) inputs are surfaced; everything else collapsed.
    assert surfaced == {"tiefe_cm", "fraesgut_klasse"}
    assert all(v["hochrisiko"] and v["tier"] == TIER_SURFACED for v in gate["surfaced"])
    # Rates land in the collapsed tier, pre-accepted but overridable.
    assert {"stundenlohn_eur", "kaltfraese_stundensatz_eur"} <= collapsed
    assert len(surfaced) + len(collapsed) == 14


async def test_compute_matches_engine_golden():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "compute"}}
    await _to_gate_b(app, cfg)
    await app.ainvoke(Command(resume={"overrides": {}}), cfg)

    state = (await app.aget_state(cfg)).values
    ekt = state["ekt_zeile"]
    assert ekt["bauverfahren"] == "BV_FRAESEN"
    assert ekt["ep_eur"] == GOLDEN_EP
    assert ekt["gp_eur"] == GOLDEN_GP
    assert state["nachweis_tabelle"]                     # full derivation tree
    assert state["beschreibung"]
    assert state.get("warnungen", []) == []


async def test_gate_b_override_changes_result():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "override"}}
    await _to_gate_b(app, cfg)
    # Override the Fraesgutklasse from 1 (verwertbar, ~free) to 3 (pechhaltig, costly).
    await app.ainvoke(Command(resume={"overrides": {"fraesgut_klasse": "3"}}), cfg)

    state = (await app.aget_state(cfg)).values
    assert Decimal(state["ekt_zeile"]["gp_eur"]) > Decimal(GOLDEN_GP)
    assert state["vorschlaege"]["fraesgut_klasse"]["status"] == STATUS_UEBERSCHRIEBEN
    # The disposal cost line is no longer zero.
    entsorgung = next(k for k in state["ekt_zeile"]["kostenlinien"]
                      if k["kostenart"] == "Entsorgung")
    assert Decimal(entsorgung["betrag_eur"]) > 0


async def test_missing_high_stakes_value_warns_and_skips_compute():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "missing"}}
    # Pin only tiefe_cm; fraesgut_klasse (no default) stays unresolved.
    gate = await _to_gate_b(app, cfg, vorgaben={"tiefe_cm": "4"})
    klasse = next(v for v in gate["surfaced"] if v["name"] == "fraesgut_klasse")
    assert klasse["wert"] is None

    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert any("fraesgut_klasse" in w for w in state.get("warnungen", []))
    assert state.get("ekt_zeile") is None


async def test_reasoning_is_narrated_each_stage():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "reasoning"}}
    await _to_gate_b(app, cfg)
    await app.ainvoke(Command(resume={"overrides": {}}), cfg)

    state = (await app.aget_state(cfg)).values
    stages = {e["stage"] for e in state["reasoning_log"] if e["kind"] == REASONING_NARRATION}
    assert {"launch", "classify_leistung", "method_review", "compute"} <= stages


async def test_method_review_offers_full_katalog():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "ga-katalog"}}
    gate = (await app.ainvoke(_payload(), cfg))["__interrupt__"][0].value
    eintrag = next(e for e in gate["katalog"] if e["leistung_key"] == "L_FRAESEN_3_45")
    assert eintrag["kandidaten"] == ["BV_FRAESEN"]
    # The whole Leistung catalog is offered, so an unclassified position can still be assigned.
    assert any(e["leistung_key"] == "L_AUFBRECHEN" for e in gate["katalog"])


async def test_method_review_cancel_aborts():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "ga-cancel"}}
    await app.ainvoke(_payload(), cfg)                        # pause at Gate A
    result = await app.ainvoke(Command(resume={"cancel": True}), cfg)
    assert "__interrupt__" not in result                      # ran to END, no further gate
    state = (await app.aget_state(cfg)).values
    assert state.get("abgebrochen") is True
    assert state.get("ekt_zeile") is None


async def test_method_review_corrects_leistung_and_rederives():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "ga-correct"}}
    await app.ainvoke(_payload(), cfg)                        # classified L_FRAESEN_3_45
    # Correct to a different Leistung + pick a candidate recipe; the worklist re-derives.
    gate_b = (await app.ainvoke(
        Command(resume={"leistung_key": "L_AUFBRECHEN", "bauverfahren_key": "BV_FRAESEN"}), cfg
    ))["__interrupt__"][0].value
    assert gate_b["stage"] == STAGE_VARIABLE_REVIEW
    state = (await app.aget_state(cfg)).values
    assert state["leistung_key"] == "L_AUFBRECHEN"
    assert state["bauverfahren_key"] == "BV_FRAESEN"


async def test_rerun_after_thread_reset_is_clean():
    """A recalculation reuses thread_id; calc.start wipes the thread first so reducer channels
    don't accumulate and the finished END state doesn't block a fresh run."""
    saver = MemorySaver()
    app = build_graph(retriever=None, checkpointer=saver)
    cfg = {"configurable": {"thread_id": "rerun"}}

    async def full_run():
        await app.ainvoke(_payload(), cfg)
        await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg)
        await app.ainvoke(Command(resume={"overrides": {}}), cfg)
        return (await app.aget_state(cfg)).values

    state1 = await full_run()
    assert state1["ekt_zeile"]["gp_eur"] == GOLDEN_GP

    await saver.adelete_thread("rerun")              # what calc.start does before a re-calc
    state2 = await full_run()
    # Fresh thread: reasoning_log did not double across runs, result reproduces.
    assert len(state2["reasoning_log"]) == len(state1["reasoning_log"])
    assert state2["ekt_zeile"]["gp_eur"] == GOLDEN_GP
