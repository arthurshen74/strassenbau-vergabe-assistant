"""Tests for the kalkulation_v2 position-calculation graph (mock mode).

Drive the full flow offline (`settings.calculator_mock`): geocoding/supplier
selection, both HITL gates (method review, variable review) and the deterministic
compute, on the L 101 fraesen slice (no material) plus a graded-material position.
The compute path is checked against the proven engine golden, and the Gate B
tiering / override / fail-soft behaviour is asserted.
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
from shared.services.calculator.lieferant_ranking import rang_lieferanten
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
    "leistung_hint": "L_FRAESEN",
}
VORGABEN = {"tiefe_cm": "4", "fraesgut_klasse": "1"}

# A graded-material position: the Langtext carries the normed designation the BM25 matcher keys on.
STS_POSITION = {
    "oz": "02.01.0001",
    "kurztext": "Schottertragschicht herstellen 0/32",
    "langtext": "Schottertragschicht 0/32 für Bk100 liefern, einbauen und verdichten.",
    "menge": "1200",
    "einheit": "m3",
    "baustoff_code": None,
    "leistung_hint": "L_STS",
}

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
    assert gate["leistung_key"] == "L_FRAESEN"
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


async def test_compute_binds_default_machine_and_computes():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "compute"}}
    await _to_gate_b(app, cfg)
    await app.ainvoke(Command(resume={"overrides": {}}), cfg)

    state = (await app.aget_state(cfg)).values
    ekt = state["ekt_zeile"]
    assert ekt["bauverfahren"] == "BV_FRAESEN"
    # bind_resources auto-selected the default Kaltfräse; its faster productivity drives the
    # cost below the conservative org-default (GOLDEN_EP 1.71) -> 0.92 €/m².
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W100CFI"
    assert ekt["ep_eur"] == "0.92"
    assert ekt["ep_eur"] != GOLDEN_EP
    by_name = {n["name"]: n for n in state["nachweis_tabelle"]}
    assert "Wirtgen W 100 CFi" in (by_name["kaltfraese_stundensatz_eur"]["beleg"] or "")
    assert state["beschreibung"]
    assert state.get("warnungen", []) == []


async def test_gate_a_machine_pick_changes_the_ekt():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "ga-machine"}}
    await app.ainvoke(_payload(), cfg)                                      # Gate A interrupt
    # Pick the larger/faster Kaltfräse explicitly in the Gate A resume.
    await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN",
                                       "maschinen": {"AA_KALTFRAESE": "WIRTGEN_W150CFI"}}), cfg)
    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"
    assert state["ekt_zeile"]["ep_eur"] != "0.92"      # differs from the default W100 result


async def test_machine_default_right_sizes_to_target_window(monkeypatch):
    # 7800 m²: a 16h window fits the small W100; an 8h window needs the big W150.
    monkeypatch.setattr(settings, "calculator_maschine_zielstunden", 16.0)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "rs-16"}}
    gate = (await app.ainvoke(_payload(), cfg))["__interrupt__"][0].value
    assert gate["maschinen_default"]["AA_KALTFRAESE"] == "WIRTGEN_W100CFI"

    monkeypatch.setattr(settings, "calculator_maschine_zielstunden", 8.0)
    app2 = build_graph(retriever=None)
    cfg2 = {"configurable": {"thread_id": "rs-8"}}
    gate2 = (await app2.ainvoke(_payload(), cfg2))["__interrupt__"][0].value
    assert gate2["maschinen_default"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"
    # The right-sized default flows through bind_resources to the bound machine.
    await app2.ainvoke(
        Command(resume={"bauverfahren_key": "BV_FRAESEN", "maschinen": gate2["maschinen_default"]}), cfg2
    )
    await app2.ainvoke(Command(resume={"overrides": {}}), cfg2)
    state = (await app2.aget_state(cfg2)).values
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"


async def test_material_position_surfaces_baustoff_suggestion():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "mat-suggest"}}
    gate = (await app.ainvoke({"position": dict(STS_POSITION), "vorgaben": {}}, cfg))[
        "__interrupt__"
    ][0].value
    v = gate["baustoff_vorschlag"]
    assert v["code"] == "STS_0_32"                      # grounded to a real catalog code
    assert v["auto"] is False                           # ~0.58 < default 0.6 -> surfaced for HITL
    assert v["treffer"][1]["code"] == "FSS_0_32"        # the close runner-up the human can pick


async def test_fraesen_position_has_no_baustoff_suggestion():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "no-mat"}}
    gate = (await app.ainvoke(_payload(), cfg))["__interrupt__"][0].value
    assert gate["baustoff_vorschlag"] is None           # milling consumes no material
    assert gate["lieferanten_vorschlag"] == {}          # ... so no supplier picker either


async def test_supplier_drives_material_price_and_antransport(monkeypatch):
    """A graded-material position: the chosen supplier feeds BOTH the ex-works material price and
    the inbound Antransport distance, and both reach the audit (plan §3, §6.11)."""
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)  # auto-apply STS_0_32
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "supplier"}}

    gate_a = (await app.ainvoke({"position": dict(STS_POSITION), "vorgaben": {}}, cfg))[
        "__interrupt__"][0].value
    vorschlag = gate_a["lieferanten_vorschlag"]["STS_0_32"]
    assert vorschlag["angebote"]                                   # ranked, cheapest first
    assert vorschlag["default"] == vorschlag["angebote"][0]["code"]

    # The cheapest-delivered supplier the graph's default mirrors (mock route = haversine).
    cheapest = (await rang_lieferanten("STS_0_32", Decimal("51.42"), Decimal("10.81")))[0]

    gate_b = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg))[
        "__interrupt__"][0].value
    dist = {v["name"]: v for v in gate_b["collapsed"]}["entfernung_lieferant_km"]
    assert dist["wert"] == str(cheapest.strasse_km)               # supplier road km, not the 10 km default
    assert "Google Routes" in (dist["beleg"] or "")

    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["lieferant_code"] == cheapest.code
    by_name = {n["name"]: n for n in state["nachweis_tabelle"]}
    assert by_name["materialpreis_eur_pro_t"]["wert"] == str(cheapest.werk_eur_pro_t)  # supplier price override
    assert "Lieferant" in (by_name["materialpreis_eur_pro_t"]["beleg"] or "")
    kostenarten = {k["kostenart"]: Decimal(k["betrag_eur"]) for k in state["ekt_zeile"]["kostenlinien"]}
    assert kostenarten["Material"] > 0 and kostenarten["Antransport"] > 0


async def test_gate_a_supplier_pick_is_honoured(monkeypatch):
    """An explicit Gate A supplier pick wins over the cheapest-delivered default."""
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "supplier-pick"}}
    gate_a = (await app.ainvoke({"position": dict(STS_POSITION), "vorgaben": {}}, cfg))[
        "__interrupt__"][0].value
    angebote = gate_a["lieferanten_vorschlag"]["STS_0_32"]["angebote"]
    pick = angebote[1]["code"]                                     # the 2nd-cheapest, not the default
    await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER",
                                       "lieferanten": {"STS_0_32": pick}}), cfg)
    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["lieferant_code"] == pick
    assert state["lieferant_werkspreis"] == angebote[1]["werk_eur_pro_t"]


async def test_baustoff_auto_applies_above_threshold(monkeypatch):
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "mat-auto"}}
    gate = (await app.ainvoke({"position": dict(STS_POSITION), "vorgaben": {}}, cfg))[
        "__interrupt__"
    ][0].value
    assert gate["baustoff_vorschlag"]["auto"] is True
    # Resume Gate A WITHOUT an explicit Baustoff pick -> the above-threshold match auto-applies.
    await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["baustoff_code"] == "STS_0_32"


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


async def test_gate_b_override_accepts_german_decimal():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "override-de"}}
    await _to_gate_b(app, cfg)
    # A German-typed value ('5,5') must parse to 5.5, not crash the run.
    await app.ainvoke(Command(resume={"overrides": {"tiefe_cm": "5,5"}}), cfg)

    state = (await app.aget_state(cfg)).values
    tiefe = state["vorschlaege"]["tiefe_cm"]
    assert tiefe["status"] == STATUS_UEBERSCHRIEBEN
    assert Decimal(tiefe["wert"]) == Decimal("5.5")
    assert state.get("ekt_zeile") is not None              # ran through to compute


async def test_gate_b_garbage_override_warns_not_crashes():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "override-bad"}}
    await _to_gate_b(app, cfg)
    # A non-numeric override is rejected with a warning; the proposal stands and the run survives.
    await app.ainvoke(Command(resume={"overrides": {"tiefe_cm": "tief"}}), cfg)

    state = (await app.aget_state(cfg)).values
    assert any("tiefe_cm" in w for w in state.get("warnungen", []))
    assert state["vorschlaege"]["tiefe_cm"]["status"] != STATUS_UEBERSCHRIEBEN
    assert state.get("ekt_zeile") is not None              # fell back to proposal, still computed


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
    eintrag = next(e for e in gate["katalog"] if e["leistung_key"] == "L_FRAESEN")
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
    await app.ainvoke(_payload(), cfg)                        # classified L_FRAESEN
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
    gp1 = state1["ekt_zeile"]["gp_eur"]

    await saver.adelete_thread("rerun")              # what calc.start does before a re-calc
    state2 = await full_run()
    # Fresh thread: reasoning_log did not double across runs, result reproduces deterministically.
    assert len(state2["reasoning_log"]) == len(state1["reasoning_log"])
    assert state2["ekt_zeile"]["gp_eur"] == gp1
