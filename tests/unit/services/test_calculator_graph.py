"""Tests for the kalkulation_v2 position-calculation graph (mock mode).

Drive the full four-gate flow offline (`settings.calculator_mock`): project context (G1),
Leistung+Bauverfahren (G2), Material (G3, skipped for material-free recipes), and
machines+supplier+variables (G4), then the deterministic compute. The compute path is checked
against the proven engine golden; the tiering / override / fail-soft behaviour is asserted; and
the ordering fix (supplier ranking runs on the CONFIRMED material) is regression-tested.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

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
    STAGE_LEISTUNG_BV_REVIEW,
    STAGE_MATERIAL_REVIEW,
    STAGE_PROJECT_CONTEXT_REVIEW,
    STAGE_VARIABLE_REVIEW,
    STATUS_UEBERSCHRIEBEN,
    TIER_SURFACED,
)

# Confirmed project Baustelle coords (the mock geocode fixture site) drive supplier ranking now
# that the site is a project-level global; the tests seed it directly in the launch payload.
PROJEKT_KONTEXT = {"baustelle_breitengrad": "51.42", "baustelle_laengengrad": "10.81"}

# BV_FSS_GRADER has two high-stakes inputs with no catalog default (schichtdicke_m, ev2_ziel); pin
# them from chat so the STS flow runs through compute (otherwise both stay unresolved and the calc
# can't complete). Neither affects the supplier ranking / material price the STS tests assert.
STS_VORGABEN = {"schichtdicke_m": "0.30", "ev2_ziel": "100"}


def _sts_payload():
    return {
        "position": dict(STS_POSITION),
        "vorgaben": dict(STS_VORGABEN),
        "projekt_kontext": dict(PROJEKT_KONTEXT),
    }

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
    """Fräsen (material-free): start, step through Gate 2, return the Gate 4 (variable) payload.
    Material-free positions skip Gate 3, so a single Bauverfahren resume reaches Gate 4."""
    result = await app.ainvoke(_payload(vorgaben), cfg)
    assert result["__interrupt__"][0].value["stage"] == STAGE_LEISTUNG_BV_REVIEW
    result = await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg)
    assert result["__interrupt__"][0].value["stage"] == STAGE_VARIABLE_REVIEW
    return result["__interrupt__"][0].value


async def _sts_to_gate4(app, cfg, material=None):
    """STS (material): start, confirm Bauverfahren (Gate 2), confirm Material (Gate 3), return the
    Gate 4 payload. `material` is the Gate-3 resume; the default (`baustoff_code=None`) accepts the
    auto/BM25 default (the interrupt payload must be non-empty for LangGraph to resume it)."""
    await app.ainvoke(_sts_payload(), cfg)
    res = await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg)
    assert res["__interrupt__"][0].value["stage"] == STAGE_MATERIAL_REVIEW
    res = await app.ainvoke(Command(resume=material or {"baustoff_code": None}), cfg)
    assert res["__interrupt__"][0].value["stage"] == STAGE_VARIABLE_REVIEW
    return res["__interrupt__"][0].value


async def test_leistung_bv_review_is_gate_2():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g2"}}
    result = await app.ainvoke(_payload(), cfg)
    gate = result["__interrupt__"][0].value
    assert gate["stage"] == STAGE_LEISTUNG_BV_REVIEW
    assert gate["leistung_key"] == "L_FRAESEN"
    assert gate["bauverfahren_kandidaten"] == ["BV_FRAESEN"]
    assert gate["bauverfahren_default"] == "BV_FRAESEN"
    assert "baustoff_vorschlag" not in gate            # material is decided at Gate 3, not here


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


async def test_gate_4_machine_pick_changes_the_ekt():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g4-machine"}}
    await _to_gate_b(app, cfg)                                              # at Gate 4
    # Pick the larger/faster Kaltfräse at Gate 4 -> its rates are re-bound before compute.
    await app.ainvoke(Command(resume={"overrides": {},
                                      "maschinen": {"AA_KALTFRAESE": "WIRTGEN_W150CFI"}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"
    assert state["ekt_zeile"]["ep_eur"] != "0.92"      # differs from the default W100 result


async def test_machine_default_right_sizes_to_target_window(monkeypatch):
    # 7800 m²: a 16h window fits the small W100; an 8h window needs the big W150. The right-sized
    # default is bound in bind_resources and shown at Gate 4 as `gewaehlte_maschinen`.
    monkeypatch.setattr(settings, "calculator_maschine_zielstunden", 16.0)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "rs-16"}}
    gate = await _to_gate_b(app, cfg)
    assert gate["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W100CFI"

    monkeypatch.setattr(settings, "calculator_maschine_zielstunden", 8.0)
    app2 = build_graph(retriever=None)
    cfg2 = {"configurable": {"thread_id": "rs-8"}}
    gate2 = await _to_gate_b(app2, cfg2)
    assert gate2["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"
    await app2.ainvoke(Command(resume={"overrides": {}}), cfg2)
    state = (await app2.aget_state(cfg2)).values
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W150CFI"


async def test_material_gate_surfaces_baustoff_suggestion():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "mat-suggest"}}
    await app.ainvoke(_sts_payload(), cfg)
    gate = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg))[
        "__interrupt__"][0].value
    assert gate["stage"] == STAGE_MATERIAL_REVIEW
    v = gate["baustoff_vorschlag"]
    assert v["code"] == "STS_0_32"                      # grounded to a real catalog code
    assert v["auto"] is False                           # ~0.58 < default 0.6 -> surfaced for HITL
    assert v["treffer"][1]["code"] == "FSS_0_32"        # the close runner-up the human can pick


async def test_fraesen_position_skips_material_gate():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "no-mat"}}
    await app.ainvoke(_payload(), cfg)                                      # Gate 2
    # Milling consumes no material -> Gate 3 is skipped; the next gate is Gate 4.
    res = await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg)
    gate = res["__interrupt__"][0].value
    assert gate["stage"] == STAGE_VARIABLE_REVIEW
    assert gate["lieferanten_vorschlag"] == {}          # ... and no supplier picker either


async def test_supplier_drives_material_price_and_antransport(monkeypatch):
    """A graded-material position: the chosen supplier feeds BOTH the ex-works material price and
    the inbound Antransport distance, and both reach the audit. Ranking runs AFTER Gate 3."""
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)  # auto-apply STS_0_32
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "supplier"}}

    gate_4 = await _sts_to_gate4(app, cfg)                          # accept the auto Baustoff
    vorschlag = gate_4["lieferanten_vorschlag"]["STS_0_32"]
    assert vorschlag["angebote"]                                    # ranked, cheapest first
    assert vorschlag["default"] == vorschlag["angebote"][0]["code"]

    # The cheapest-delivered supplier the graph's default mirrors (mock route = haversine).
    cheapest = (await rang_lieferanten("STS_0_32", Decimal("51.42"), Decimal("10.81"))).angebote[0]
    dist = {v["name"]: v for v in gate_4["collapsed"]}["entfernung_lieferant_km"]
    assert dist["wert"] == str(cheapest.strasse_km)                # supplier road km, not the 10 km default
    assert "Google Routes" in (dist["beleg"] or "")

    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["lieferant_code"] == cheapest.code
    by_name = {n["name"]: n for n in state["nachweis_tabelle"]}
    assert by_name["materialpreis_eur_pro_t"]["wert"] == str(cheapest.werk_eur_pro_t)  # supplier price override
    assert "Lieferant" in (by_name["materialpreis_eur_pro_t"]["beleg"] or "")
    kostenarten = {k["kostenart"]: Decimal(k["betrag_eur"]) for k in state["ekt_zeile"]["kostenlinien"]}
    assert kostenarten["Material"] > 0 and kostenarten["Antransport"] > 0


async def test_gate_4_supplier_pick_is_honoured(monkeypatch):
    """An explicit Gate 4 supplier pick wins over the cheapest-delivered default."""
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "supplier-pick"}}
    gate_4 = await _sts_to_gate4(app, cfg)
    angebote = gate_4["lieferanten_vorschlag"]["STS_0_32"]["angebote"]
    pick = angebote[1]["code"]                                      # the 2nd-cheapest, not the default
    await app.ainvoke(Command(resume={"overrides": {}, "lieferanten": {"STS_0_32": pick}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["lieferant_code"] == pick
    assert state["lieferant_werkspreis"] == angebote[1]["werk_eur_pro_t"]


async def test_material_correction_reranks_suppliers():
    """Regression (the whole point of the split): correcting the Baustoff at Gate 3 re-ranks
    suppliers for the CORRECTED material. Pre-split, ranking ran on the proposed material and a
    correction stranded it into the catalog fallback (the 524.90-bitumen-as-asphalt incident)."""
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "mat-correct"}}
    # Gate 3 proposes STS_0_32; the human corrects it to the runner-up FSS_0_32.
    gate_4 = await _sts_to_gate4(app, cfg, material={"baustoff_code": "FSS_0_32"})
    assert "FSS_0_32" in gate_4["lieferanten_vorschlag"]           # ranked for the CORRECTED material
    assert "STS_0_32" not in gate_4["lieferanten_vorschlag"]

    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    assert state["baustoff_code"] == "FSS_0_32"
    assert state["lieferant_code"] is not None                     # supplier-driven, not catalog fallback
    by_name = {n["name"]: n for n in state["nachweis_tabelle"]}
    assert "Lieferant" in (by_name["materialpreis_eur_pro_t"]["beleg"] or "")


# Project context the stub loader returns (the run_service loader is exercised separately).
BASE_KONTEXT = {
    "baustelle_breitengrad": "51.42",
    "baustelle_laengengrad": "10.81",
    "deponie_location": "Deponie Sangerhausen",
    "entfernung_deponie_km": "12.0",
    "strip_length_m": "5100",
    "strip_width_m": "1.0",
    "fraesgut_klasse": "1",
}


def _stub_context_seams():
    """A loader returning a fixed project context + a saver recording the review override."""
    saved: dict = {}

    async def loader(project_uuid, _kandidaten):
        return {"projekt_kontext": dict(BASE_KONTEXT)}

    async def saver(project_uuid, updates):
        saved.update(updates)
        return {**BASE_KONTEXT, **updates}

    return loader, saver, saved


async def test_project_context_review_gate_overrides_and_flows():
    """The Gate-1 project-context gate fires first; an override saves and flows into the calc: the
    project deponie distance (routed) replaces the 10 km default, and the Fräsgutklasse the
    Kalkulator overrode is the one surfaced at Gate 4."""
    loader, saver, saved = _stub_context_seams()
    app = build_graph(retriever=None, project_context_loader=loader, project_context_saver=saver)
    cfg = {"configurable": {"thread_id": "pctx"}}

    res = await app.ainvoke(
        {"position": dict(POSITION), "vorgaben": {"tiefe_cm": "4"}, "project_uuid": uuid4()}, cfg
    )
    gate = res["__interrupt__"][0].value
    assert gate["stage"] == STAGE_PROJECT_CONTEXT_REVIEW
    assert gate["projekt_kontext"]["entfernung_deponie_km"] == "12.0"

    # Confirm the context, overriding the Fräsgutklasse; the saver persists just that field.
    res2 = await app.ainvoke(Command(resume={"projekt_kontext": {"fraesgut_klasse": "2"}}), cfg)
    assert saved == {"fraesgut_klasse": "2"}
    assert res2["__interrupt__"][0].value["stage"] == STAGE_LEISTUNG_BV_REVIEW

    gate_b = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg))[
        "__interrupt__"][0].value
    assert gate_b["stage"] == STAGE_VARIABLE_REVIEW               # fräsen skips Gate 3
    fraesgut = next(v for v in gate_b["surfaced"] if v["name"] == "fraesgut_klasse")
    assert fraesgut["wert"] == "2"                          # the project default (overridden) is surfaced
    deponie = {v["name"]: v for v in gate_b["collapsed"]}["entfernung_deponie_km"]
    assert deponie["wert"] == "12.0"                        # routed project value, not the 10 km default

    await app.ainvoke(Command(resume={"overrides": {}}), cfg)
    state = (await app.aget_state(cfg)).values
    by_name = {n["name"]: n for n in state["nachweis_tabelle"]}
    assert by_name["entfernung_deponie_km"]["wert"] == "12.0"
    assert "Deponie Sangerhausen" in (by_name["entfernung_deponie_km"]["beleg"] or "")
    assert by_name["fraesgut_klasse"]["wert"] == "2"


async def test_project_context_review_skipped_without_seams():
    """With no project-context seams (standalone) the gate is a no-op: Gate 2 is first."""
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "pctx-skip"}}
    res = await app.ainvoke(_payload(), cfg)
    assert res["__interrupt__"][0].value["stage"] == STAGE_LEISTUNG_BV_REVIEW


def _blocking_context_seams():
    """A loader whose Baustelle has an address but NO geocoded coordinates (geocode failed); the
    saver resolves coordinates only when a specific corrected address is provided."""
    no_coords = {
        "baustelle_location": "L 151 (unklar)",
        "baustelle_status": "fehlgeschlagen",
        "deponie_location": "Deponie Sangerhausen",
        "entfernung_deponie_km": "12.0",
        "strip_length_m": "5100",
        "strip_width_m": "1.0",
        "fraesgut_klasse": "1",
    }

    async def loader(project_uuid, _kandidaten):
        return {"projekt_kontext": dict(no_coords)}

    async def saver(project_uuid, updates):
        neu = {**no_coords, **updates}
        if updates.get("baustelle_location") == "Blankenheim":
            neu["baustelle_breitengrad"] = "51.42"
            neu["baustelle_laengengrad"] = "10.81"
            neu["baustelle_status"] = "aufgeloest"
        return neu

    return loader, saver


async def test_project_context_gate_blocks_until_baustelle_geocoded():
    """A required global (Baustelle) that has no coordinates blocks the run at the review gate:
    confirming without fixing it re-blocks; a corrected, geocodable address clears it to Gate 2."""
    loader, saver = _blocking_context_seams()
    app = build_graph(retriever=None, project_context_loader=loader, project_context_saver=saver)
    cfg = {"configurable": {"thread_id": "pctx-block"}}

    res = await app.ainvoke(
        {"position": dict(POSITION), "vorgaben": {}, "project_uuid": uuid4()}, cfg)
    gate = res["__interrupt__"][0].value
    assert gate["stage"] == STAGE_PROJECT_CONTEXT_REVIEW
    assert "baustelle_location" in gate["fehlende_erforderliche"]
    assert gate["fehler"]

    # Confirming without a valid Baustelle re-blocks at the same gate (still no coordinates).
    res2 = await app.ainvoke(Command(resume={"projekt_kontext": {}}), cfg)
    gate2 = res2["__interrupt__"][0].value
    assert gate2["stage"] == STAGE_PROJECT_CONTEXT_REVIEW
    assert gate2["fehler"]

    # A corrected address geocodes -> the gate clears and Gate 2 is next.
    res3 = await app.ainvoke(
        Command(resume={"projekt_kontext": {"baustelle_location": "Blankenheim"}}), cfg)
    assert res3["__interrupt__"][0].value["stage"] == STAGE_LEISTUNG_BV_REVIEW


async def test_project_context_gate_cancel_aborts():
    """Cancelling the project-context gate stops the run (no EKT) instead of computing without a
    valid Baustelle."""
    loader, saver = _blocking_context_seams()
    app = build_graph(retriever=None, project_context_loader=loader, project_context_saver=saver)
    cfg = {"configurable": {"thread_id": "pctx-cancel"}}

    await app.ainvoke({"position": dict(POSITION), "vorgaben": {}, "project_uuid": uuid4()}, cfg)
    res = await app.ainvoke(Command(resume={"cancel": True}), cfg)
    assert "__interrupt__" not in res
    state = (await app.aget_state(cfg)).values
    assert state.get("abgebrochen") is True
    assert state.get("ekt_zeile") is None


async def test_baustoff_auto_applies_above_threshold(monkeypatch):
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "mat-auto"}}
    await app.ainvoke(_sts_payload(), cfg)
    gate = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg))[
        "__interrupt__"][0].value
    assert gate["stage"] == STAGE_MATERIAL_REVIEW
    assert gate["baustoff_vorschlag"]["auto"] is True
    # Resume Gate 3 WITHOUT an explicit pick -> the above-threshold match auto-applies.
    await app.ainvoke(Command(resume={"baustoff_code": None}), cfg)
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
    assert {"launch", "classify_leistung", "leistung_bv_review", "compute"} <= stages


async def test_leistung_bv_review_offers_full_katalog():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g2-katalog"}}
    gate = (await app.ainvoke(_payload(), cfg))["__interrupt__"][0].value
    eintrag = next(e for e in gate["katalog"] if e["leistung_key"] == "L_FRAESEN")
    assert eintrag["kandidaten"] == ["BV_FRAESEN"]
    # The whole Leistung catalog is offered, so an unclassified position can still be assigned.
    assert any(e["leistung_key"] == "L_AUFBRECHEN" for e in gate["katalog"])


async def test_leistung_bv_review_cancel_aborts():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g2-cancel"}}
    await app.ainvoke(_payload(), cfg)                        # pause at Gate 2
    result = await app.ainvoke(Command(resume={"cancel": True}), cfg)
    assert "__interrupt__" not in result                      # ran to END, no further gate
    state = (await app.aget_state(cfg)).values
    assert state.get("abgebrochen") is True
    assert state.get("ekt_zeile") is None


async def test_material_gate_cancel_aborts(monkeypatch):
    monkeypatch.setattr(settings, "calculator_baustoff_match_threshold", 0.55)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g3-cancel"}}
    await app.ainvoke(_sts_payload(), cfg)                                        # Gate 2
    await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FSS_GRADER"}), cfg)  # -> Gate 3
    result = await app.ainvoke(Command(resume={"cancel": True}), cfg)
    assert "__interrupt__" not in result
    state = (await app.aget_state(cfg)).values
    assert state.get("abgebrochen") is True
    assert state.get("ekt_zeile") is None


async def test_leistung_bv_review_corrects_leistung_and_rederives():
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "g2-correct"}}
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
