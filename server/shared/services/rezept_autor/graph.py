"""Rezept-Autor graph (Part B — deliberately dumb): describe → validate → human review.

Three nodes: `entwerfen` drafts a `KatalogBundle` (one LLM call, injected as `entwerfer`), `pruefen`
validates it (injected `pruefer`), and `rezept_review` is a HITL interrupt carrying the bundle, the
validation report and the supersede flags. Validation errors loop back to `entwerfen` (up to
`MAX_VERSUCHE`, then the errors are surfaced to the human); the reviewer either sends feedback (loops
back), confirms (persists the draft via `speichern`, and — with `aktivieren` — activates + reloads),
or discards.

DB access stays out of the graph: `entwerfer`/`pruefer`/`speichern`/`aktivieren` are injected async
callables (the run_service closes them over the LLM and the KatalogService; tests inject fakes). The
compiler intelligence and the real prompt are Part C — out of scope here.
"""

from __future__ import annotations

import operator
from typing import Annotated, Awaitable, Callable, TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from shared.models.katalog import BundleBericht, KatalogBundle

# Interrupt discriminator (mirrored in the UI's InterruptPanel).
STAGE_REZEPT_REVIEW = "rezept_review"
REASONING_NARRATION = "narration"

# Max entwerfen attempts before surfacing validation errors to the human.
MAX_VERSUCHE = 3

Entwerfer = Callable[[str, list[str], str | None], Awaitable[KatalogBundle]]
Pruefer = Callable[[KatalogBundle], Awaitable[BundleBericht]]
Speichern = Callable[[KatalogBundle], Awaitable[UUID]]
Aktivieren = Callable[[UUID], Awaitable[BundleBericht]]


class RezeptAutorState(TypedDict, total=False):
    beschreibung: str
    versuche: int
    bundle: dict  # KatalogBundle as JSON
    bericht: dict  # BundleBericht as JSON
    feedback: str | None
    reasoning_log: Annotated[list[dict], operator.add]
    gespeichert: bool
    aktiviert: bool
    verworfen: bool
    bundle_uuid: str | None


def _reason(text: str) -> dict:
    return {"stage": STAGE_REZEPT_REVIEW, "kind": REASONING_NARRATION, "text": text}


def build_graph(
    *,
    entwerfer: Entwerfer,
    pruefer: Pruefer,
    speichern: Speichern,
    aktivieren: Aktivieren,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the recipe-author graph. The four DB/LLM seams are injected as async callables."""

    async def entwerfen(state: RezeptAutorState) -> dict:
        versuche = state.get("versuche", 0) + 1
        fehler = (state.get("bericht") or {}).get("fehler", []) if state.get("bundle") else []
        feedback = state.get("feedback")
        bundle = await entwerfer(state["beschreibung"], fehler, feedback)
        hinweis = "überarbeitet" if versuche > 1 else "entworfen"
        return {
            "bundle": bundle.model_dump(mode="json"),
            "versuche": versuche,
            "feedback": None,
            "reasoning_log": [_reason(f"Rezept {hinweis} (Versuch {versuche}).")],
        }

    async def pruefen(state: RezeptAutorState) -> dict:
        bericht = await pruefer(KatalogBundle.model_validate(state["bundle"]))
        text = (
            "Rezept ist gültig."
            if bericht.gueltig
            else f"Validierung: {len(bericht.fehler)} Fehler."
        )
        return {"bericht": bericht.model_dump(mode="json"), "reasoning_log": [_reason(text)]}

    def _route_after_pruefen(state: RezeptAutorState) -> str:
        bericht = state["bericht"]
        if bericht["fehler"] and state["versuche"] < MAX_VERSUCHE:
            return "entwerfen"
        return "rezept_review"

    async def rezept_review(state: RezeptAutorState) -> dict:
        antwort = interrupt(
            {"stage": STAGE_REZEPT_REVIEW, "bundle": state["bundle"], "bericht": state["bericht"]}
        ) or {}
        if antwort.get("feedback"):
            return {"feedback": antwort["feedback"], "reasoning_log": [_reason("Feedback erhalten — überarbeite das Rezept.")]}
        if not antwort.get("bestaetigt"):
            return {"verworfen": True, "reasoning_log": [_reason("Rezept verworfen.")]}
        bundle = KatalogBundle.model_validate(state["bundle"])
        bundle_uuid = await speichern(bundle)
        aktiviert = False
        if antwort.get("aktivieren"):
            await aktivieren(bundle_uuid)
            aktiviert = True
        text = "Rezept gespeichert und aktiviert." if aktiviert else "Rezept als Entwurf gespeichert."
        return {
            "gespeichert": True,
            "aktiviert": aktiviert,
            "bundle_uuid": str(bundle_uuid),
            "reasoning_log": [_reason(text)],
        }

    def _route_after_review(state: RezeptAutorState) -> str:
        return "entwerfen" if state.get("feedback") else END

    g = StateGraph(RezeptAutorState)
    g.add_node("entwerfen", entwerfen)
    g.add_node("pruefen", pruefen)
    g.add_node("rezept_review", rezept_review)
    g.add_edge(START, "entwerfen")
    g.add_edge("entwerfen", "pruefen")
    g.add_conditional_edges(
        "pruefen", _route_after_pruefen, {"entwerfen": "entwerfen", "rezept_review": "rezept_review"}
    )
    g.add_conditional_edges("rezept_review", _route_after_review, {"entwerfen": "entwerfen", END: END})
    return g.compile(checkpointer=checkpointer or MemorySaver())
