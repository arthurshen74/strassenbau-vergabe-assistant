"""Tests for the live (non-mock) LLM/RAG wiring of the position-calculation graph.

A fake LLMClient + retriever stand in for the real sites so the graph's cascade,
classification, chat-extraction and narration plumbing is exercised deterministically:
the structured outputs are canned, and the engine compute stays real. The fraesen
slice still lands on the engine golden when the inputs match the fixture.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.types import Command

from shared.clients.llm.client import MESSAGE_CONTENT
from shared.config import settings
from shared.models.enums import PromptType
from shared.services.calculator.graph import build_graph
from shared.services.calculator.llm_calls import (
    ChatWerte,
    ChatWertZuweisung,
    LeistungKlassifikation,
    WertExtraktion,
)
from shared.services.calculator.state import (
    STAGE_LEISTUNG_BV_REVIEW,
    STAGE_VARIABLE_REVIEW,
)

POSITION = {
    "oz": "01.02.0006",
    "kurztext": "Asphaltbefestigung abfraesen, 3 bis 4,5 cm",
    "langtext": "Vorhandene Asphaltbefestigung abfraesen und entsorgen, Frästiefe 4 cm.",
    "hinweis": None,
    "menge": "7800",
    "einheit": "m2",
    "baustoff_code": None,
}

_PROMPT_TYPES = (
    PromptType.EKT_LEISTUNG_CLASSIFY,
    PromptType.EKT_CHAT_VALUES,
    PromptType.EKT_LANGTEXT_EXTRACT,
    PromptType.EKT_OUTPUT_NARRATE,
)
PROMPTS = {
    pt: SimpleNamespace(model_name="fake", system_prompt="sys", temperature=None,
                        reasoning_effort=None, prompt_type=pt, version=1)
    for pt in _PROMPT_TYPES
}


class FakeLLM:
    """Dispatches chat_with_reasoning on the requested output_model; records call names."""

    def __init__(self, *, klassifikation, extraktionen, chatwerte=None, narration="Erläuterung."):
        self.klassifikation = klassifikation
        self.extraktionen = extraktionen          # name -> WertExtraktion
        self.chatwerte = chatwerte or ChatWerte(zuweisungen=[])
        self.narration = narration
        self.calls: list[str] = []

    async def chat_with_reasoning(self, *, model, messages, output_model, **kw):
        self.calls.append(output_model.__name__)
        if output_model is LeistungKlassifikation:
            return self.klassifikation, None
        if output_model is ChatWerte:
            return self.chatwerte, None
        if output_model is WertExtraktion:
            content = messages[-1][MESSAGE_CONTENT]
            for name, ext in self.extraktionen.items():
                if f'"name": "{name}"' in content:
                    return ext, None
            return WertExtraktion(gefunden=False, wert=None, konfidenz=0.0), None
        raise AssertionError(f"unexpected output_model {output_model}")

    async def chat(self, *, model, messages, **kw):
        self.calls.append("narrate")
        return self.narration


async def _retr(_query: str) -> list[str]:
    return []


@pytest.fixture(autouse=True)
def _live(monkeypatch):
    monkeypatch.setattr(settings, "calculator_mock", False)


def _app(llm):
    return build_graph(retriever=_retr, llm=llm, prompts=PROMPTS)


CLASSIFY_OK = LeistungKlassifikation(
    reasoning=["Langtext nennt 'abfraesen'."], leistung_key="L_FRAESEN",
    konfidenz=0.95, notizen="Fräsen 3-4,5 cm.")
# tiefe_cm read from the Langtext; fraesgut_klasse not in the docs (no Schadstoffgutachten).
EXTRAKT = {
    "tiefe_cm": WertExtraktion(reasoning=["'Frästiefe 4 cm'."], gefunden=True, wert="4",
                               konfidenz=0.9, beleg="Frästiefe 4 cm"),
}


async def test_live_full_flow_matches_golden():
    llm = FakeLLM(klassifikation=CLASSIFY_OK, extraktionen=EXTRAKT)
    app = _app(llm)
    cfg = {"configurable": {"thread_id": "live-golden"}}

    gate_a = (await app.ainvoke({"position": dict(POSITION), "chat_verlauf": []}, cfg))["__interrupt__"][0].value
    assert gate_a["stage"] == STAGE_LEISTUNG_BV_REVIEW
    assert gate_a["leistung_key"] == "L_FRAESEN"

    gate_b = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg))["__interrupt__"][0].value
    assert gate_b["stage"] == STAGE_VARIABLE_REVIEW
    surfaced = {v["name"]: v for v in gate_b["surfaced"]}
    # tiefe_cm resolved from Langtext; fraesgut_klasse unresolved (RAG empty) — both surfaced.
    assert surfaced["tiefe_cm"]["wert"] == "4"
    assert surfaced["tiefe_cm"]["quelle"] == "langtext"
    assert surfaced["fraesgut_klasse"]["wert"] is None

    # Override the unresolved high-stakes class to match the fixture (1 = verwertbar).
    await app.ainvoke(Command(resume={"overrides": {"fraesgut_klasse": "1"}}), cfg)
    state = (await app.aget_state(cfg)).values
    # The default Kaltfräse is auto-bound -> machine-driven cost (0.92, below the org 1.71).
    assert state["gewaehlte_maschinen"]["AA_KALTFRAESE"] == "WIRTGEN_W100CFI"
    assert state["ekt_zeile"]["ep_eur"] == "0.92"
    assert state["beschreibung"] == "Erläuterung."
    assert "LeistungKlassifikation" in llm.calls
    assert "WertExtraktion" in llm.calls
    assert "narrate" in llm.calls


async def test_live_mit_default_falls_through_hitl_to_default():
    llm = FakeLLM(klassifikation=CLASSIFY_OK, extraktionen=EXTRAKT)
    app = _app(llm)
    cfg = {"configurable": {"thread_id": "live-default"}}
    await app.ainvoke({"position": dict(POSITION), "chat_verlauf": []}, cfg)
    gate_b = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg))["__interrupt__"][0].value

    collapsed = {v["name"]: v for v in gate_b["collapsed"]}
    # anzahl_arbeiter cascade is [HITL, KONSTANTE]: HITL is skipped, the default is used.
    assert collapsed["anzahl_arbeiter"]["wert"] == "2"
    assert collapsed["anzahl_arbeiter"]["quelle"] == "konstante"
    assert collapsed["entfernung_deponie_km"]["wert"] == "10"


async def test_live_chat_value_pins_source_zero():
    chat = ChatWerte(zuweisungen=[ChatWertZuweisung(
        name="fraesgut_klasse", wert="3", beleg="der Nutzer sagte: pechhaltig")])
    llm = FakeLLM(klassifikation=CLASSIFY_OK, extraktionen=EXTRAKT, chatwerte=chat)
    app = _app(llm)
    cfg = {"configurable": {"thread_id": "live-chat"}}
    transcript = [{"role": "user", "content": "Die Fräsgutklasse ist pechhaltig."}]
    await app.ainvoke({"position": dict(POSITION), "chat_verlauf": transcript}, cfg)
    gate_b = (await app.ainvoke(Command(resume={"bauverfahren_key": "BV_FRAESEN"}), cfg))["__interrupt__"][0].value

    surfaced = {v["name"]: v for v in gate_b["surfaced"]}
    # The chat pinned fraesgut_klasse (source 0) -> resolved with HITL provenance, not unresolved.
    assert surfaced["fraesgut_klasse"]["wert"] == "3"
    assert surfaced["fraesgut_klasse"]["quelle"] == "hitl"
    assert "ChatWerte" in llm.calls
