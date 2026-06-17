"""Tests for the deterministic glue in the calculator graph.

Covers the numeric coercion between the LLM's verbatim document reads and the
formula schemas (German decimal commas, "ca."/unit noise), derive_drivers'
fail-soft contract (missing or unparseable inputs become review flags instead of
crashing the run), and the driver-confirmation HITL interrupt.
"""

from __future__ import annotations

from langgraph.types import Command

from shared.config import settings
from shared.services.calculator.graph import (
    PROVENANCE_CHAT,
    PROVENANCE_HITL,
    REASONING_LLM,
    REASONING_NARRATION,
    STAGE_DRIVER_CONFIRMATION,
    STAGE_EKT_REVIEW,
    build_graph,
    coerce_numeric,
    derive_drivers,
    driver_catalog,
)


def test_coerce_numeric_german_decimal_comma():
    assert coerce_numeric("ca. 0,30") == 0.30


def test_coerce_numeric_with_comparator_and_unit():
    assert coerce_numeric(">= 50,0 cm") == 50.0


def test_coerce_numeric_passthrough_numbers():
    assert coerce_numeric(20) == 20.0
    assert coerce_numeric(0.5) == 0.5


def test_coerce_numeric_plain_string():
    assert coerce_numeric("12") == 12.0


def test_coerce_numeric_unparseable_returns_none():
    assert coerce_numeric("schmaler Streifen") is None
    assert coerce_numeric(None) is None


def test_derive_drivers_fails_soft_on_missing_inputs():
    state = {
        "work_type": "fss_herstellen",
        "drivers": {
            "material_spec": "FSS 0/32 B2",
            "einbaudicke_cm": 20.0,
            "strip_length_m": None,        # not found in documents
            "strip_width_m": 0.3,
            "loss_profile": "standard",
        },
    }
    out = derive_drivers(state)

    # layer_volume blocks on the None length; order_tonnage blocks on the
    # missing layer_volume it depends on. Run continues either way.
    wheres = [f["where"] for f in out["review_flags"]]
    assert wheres == ["derived:layer_volume_m3", "derived:order_tonnage_t"]
    assert all(f["kind"] == "blocked" for f in out["review_flags"])
    assert "layer_volume_m3" not in out["drivers"]
    assert "order_tonnage_t" not in out["drivers"]


def test_derive_drivers_computes_when_inputs_present():
    state = {
        "work_type": "fss_herstellen",
        "drivers": {
            "material_spec": "FSS 0/32 B2",
            "einbaudicke_cm": 20.0,
            "strip_length_m": 1000.0,
            "strip_width_m": 0.5,
            "loss_profile": "elevated",
        },
    }
    out = derive_drivers(state)

    assert out["review_flags"] == []
    assert out["drivers"]["layer_volume_m3"] == 100.0
    assert out["drivers"]["order_tonnage_t"] == 231.0   # 100 * 2.10 * 1.10


POSITION = {
    "oz": "01.03.0004",
    "kurztext": "Frostschutzschicht herstellen",
    "langtext": "Frostschutzschicht herstellen, Baustoffgemisch 0/32.",
    "boq_menge": 100.0,
    "boq_einheit": "m3",
}


async def test_driver_confirmation_interrupt_flow(monkeypatch):
    monkeypatch.setattr(settings, "calculator_mock", True)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "confirm-flow"}}

    # First pause: the confirm-marked driver (strip_length_m) awaits the human.
    result = await app.ainvoke({"position": POSITION}, cfg)
    payload = result["__interrupt__"][0].value
    assert payload["stage"] == STAGE_DRIVER_CONFIRMATION
    assert [d["id"] for d in payload["confirm"]] == ["strip_length_m"]
    assert payload["confirm"][0]["value"] == 1000

    # The human corrects the assumed length; German comma is coerced.
    result = await app.ainvoke(
        Command(resume={"drivers": {"strip_length_m": "950,0"}}), cfg
    )
    payload = result["__interrupt__"][0].value
    assert payload["stage"] == STAGE_EKT_REVIEW

    state = (await app.aget_state(cfg)).values
    assert state["drivers"]["strip_length_m"] == 950.0
    assert state["driver_provenance"]["strip_length_m"] == {
        "source": PROVENANCE_HITL, "confidence": 1.0,
    }


async def test_driver_confirmation_accept_keeps_resolved_value(monkeypatch):
    monkeypatch.setattr(settings, "calculator_mock", True)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "confirm-accept"}}

    result = await app.ainvoke({"position": POSITION}, cfg)
    assert result["__interrupt__"][0].value["stage"] == STAGE_DRIVER_CONFIRMATION

    # Empty overrides = accept everything as resolved.
    result = await app.ainvoke(Command(resume={"drivers": {}}), cfg)
    assert result["__interrupt__"][0].value["stage"] == STAGE_EKT_REVIEW

    state = (await app.aget_state(cfg)).values
    assert state["drivers"]["strip_length_m"] == 1000
    assert state["ekt"]["total_eur"] > 0

    # Approving emits the VHB 223 row; its buckets reconcile with the EKT.
    await app.ainvoke(Command(resume={"action": "approve"}), cfg)
    state = (await app.aget_state(cfg)).values
    form = state["form_223"]
    per_unit = (form["lohn_eur"] + form["stoffe_eur"]
                + form["geraete_eur"] + form["sonstiges_eur"])
    assert abs(per_unit - state["ekt"]["per_unit_eur"]) < 0.05
    assert form["zeitansatz_h"] > 0
    assert form["oz"] == POSITION["oz"]
    assert form["mengeneinheit"] == POSITION["boq_einheit"]

    # The reasoning log narrates each stage and carries the LLM's steps.
    log = state["reasoning_log"]
    texts = [e["text"] for e in log if e["kind"] == REASONING_NARRATION]
    assert "I need to assign the position to a Leistung." in texts
    assert "I need to plan the operations." in texts
    assert any(t.startswith("I need to choose the Bauweise") for t in texts)
    assert any(e["kind"] == REASONING_LLM and e["stage"] == "classify" for e in log)
    assert any(e["kind"] == REASONING_LLM and e["stage"] == "resolve_drivers"
               for e in log)
    assert any(e["kind"] == REASONING_LLM and e["stage"].startswith("operation:")
               for e in log)


def test_driver_catalog_dedups_across_registries():
    catalog = driver_catalog()
    ids = [c["id"] for c in catalog]
    assert ids == list(dict.fromkeys(ids))      # one entry per id, even across registries
    assert "strip_length_m" in ids
    assert {"id", "description", "einheit"} <= set(catalog[0])


async def test_seed_drivers_override_document_resolution(monkeypatch):
    monkeypatch.setattr(settings, "calculator_mock", True)
    app = build_graph(retriever=None)
    cfg = {"configurable": {"thread_id": "seed-flow"}}

    # The Kalkulator set strip_length_m in the pre-run chat; the mock would otherwise resolve 1000.
    result = await app.ainvoke(
        {"position": POSITION, "seed_drivers": {"strip_length_m": "250"}}, cfg
    )
    payload = result["__interrupt__"][0].value
    assert payload["stage"] == STAGE_DRIVER_CONFIRMATION
    # The confirm prompt shows the chat value (coerced), not the mock-resolved 1000.
    assert payload["confirm"][0]["value"] == 250.0

    state = (await app.aget_state(cfg)).values
    assert state["drivers"]["strip_length_m"] == 250.0
    assert state["driver_provenance"]["strip_length_m"] == {
        "source": PROVENANCE_CHAT, "confidence": 1.0,
    }
    texts = [e["text"] for e in state["reasoning_log"] if e["kind"] == REASONING_NARRATION]
    assert any("set by Kalkulator in the pre-run chat" in t for t in texts)
