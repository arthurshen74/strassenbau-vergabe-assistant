"""Integration tests for the Katalog-Chat agent surface (§10.2).

Part 1 — the canonical question set answers end-to-end through the agent's real tools (the LLM is
never invoked; each question is a scripted tool call against the seeded catalog, asserting the
answer). These are the ten §3 „Beantwortet" questions, including „Welche Lieferanten können AC 22 T S
liefern?".

Part 2 — the service path: a scripted agent stream (a tool call + its real result + an answer token)
maps to the SSE envelopes and persists the transcript.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest_asyncio
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.conversation import NewConversation
from shared.models.enums import MessageKind, PromptType
from shared.models.sse_schema import (
    DATA,
    DATA_RESULT,
    EVENT,
    EVENT_DONE,
    EVENT_FUNCTION_CALL,
    EVENT_FUNCTION_CALL_OUTPUT,
    EVENT_TEXT_DELTA,
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.katalog import KatalogRepository
from shared.repositories.messages import MessageRepository
from shared.services.katalog.chat_service import KatalogChatService
from shared.services.katalog.werkzeuge import katalog_werkzeuge
from shared.services.project_chat_agent import AgentToken, AgentToolCall, AgentToolResult

from scripts.seed.seed_katalog import seed_katalog


@pytest_asyncio.fixture(scope="module")
async def katalog_engine(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    async with engine.begin() as conn:
        repo = KatalogRepository(conn)
        await repo.alles_leeren()
        await seed_katalog(repo)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await KatalogRepository(conn).alles_leeren()


@pytest_asyncio.fixture(scope="module")
async def werkzeuge(katalog_engine: AsyncEngine) -> dict[str, BaseTool]:
    return {t.name: t for t in katalog_werkzeuge(katalog_engine)}


async def _art(werkzeuge: dict[str, BaseTool], werkzeug: str, **args: Any) -> dict[str, Any]:
    """Invoke a real @tool the way the agent would and return its artifact (the answer envelope)."""
    msg = await werkzeuge[werkzeug].ainvoke(
        {"type": "tool_call", "name": werkzeug, "args": args, "id": "c"}
    )
    return msg.artifact  # type: ignore[attr-defined]


# --- Part 1: the ten canonical questions, each through its real tool -------------------------- #
async def test_frage_uebersicht(werkzeuge: dict[str, BaseTool]) -> None:
    # „Was ist alles im Katalog? Wann zuletzt geändert und von wem?"
    u = await _art(werkzeuge, "katalog_uebersicht")
    assert u["entitaeten"]["leistungen"] > 0 and u["stand"]["benutzer"] == "seed"


async def test_frage_suche_bankett(werkzeuge: dict[str, BaseTool]) -> None:
    # „Gibt es irgendwas zu ‚Bankett'?"
    treffer = await _art(werkzeuge, "suche_katalog", text="Bankett")
    assert treffer["treffer_gesamt"] >= 1


async def test_frage_dsl_funktionen(werkzeuge: dict[str, BaseTool]) -> None:
    # „Welche Funktionen darf eine Formel benutzen?"
    dsl = await _art(werkzeuge, "zeige_dsl_funktionen")
    assert any(f["name"] == "ceil" for f in dsl["funktionen"])


async def test_frage_bauverfahren_fuer_fss(werkzeuge: dict[str, BaseTool]) -> None:
    # „Welche Bauverfahren gibt es für die FSS, und welches ist Standard?"
    l = await _art(werkzeuge, "zeige_leistung", code="L_FSS")
    assert l["bauverfahren"][0]["standard"] is True


async def test_frage_wo_wird_vorgang_eingesetzt(werkzeuge: dict[str, BaseTool]) -> None:
    # „Wo wird <Vorgang> überall eingesetzt?"
    kette = (await _art(werkzeuge, "zeige_bauverfahren", code="BV_FSS_GRADER"))["vorgaenge"]
    fund = await _art(werkzeuge, "finde_bauverfahren_mit_vorgang", vorgang_code=kette[0]["code"])
    assert any(t["code"] == "BV_FSS_GRADER" for t in fund["bauverfahren"])


async def test_frage_maschinen_fuer_kaltfraese(werkzeuge: dict[str, BaseTool]) -> None:
    # „Welche Maschinen habe ich für die Kaltfräse, und wofür wird sie gebraucht?"
    aa = await _art(werkzeuge, "zeige_ausfuehrungsart", code="AA_KALTFRAESE")
    assert aa["maschinen"] and aa["vorgaenge"]


async def test_frage_lieferanten_ac22ts(werkzeuge: dict[str, BaseTool]) -> None:
    # THE canonical question: „Welche Lieferanten können AC 22 T S liefern, und zu welchem Werkspreis?"
    fund = await _art(werkzeuge, "finde_lieferanten_fuer_baustoff", baustoff_code="ASPHALT_AC22TS")
    preise = [float(l["werkspreis_eur_pro_t"]) for l in fund["lieferanten"]]
    assert preise and preise == sorted(preise)


async def test_frage_preis_historie(werkzeuge: dict[str, BaseTool]) -> None:
    # „Was kostet <Baustoff> bei <Lieferant>, und was hat es letztes Jahr gekostet?"
    preise = await _art(werkzeuge, "zeige_preise", baustoff_code="ASPHALT_AC22TS", mit_historie=True)
    assert preise["eintraege"]


async def test_frage_formeln_am_dieselpreis(werkzeuge: dict[str, BaseTool]) -> None:
    # „Welche Formeln hängen am Dieselpreis?"
    liste = await _art(werkzeuge, "liste_formeln", referenziert_variable="kraftstoffpreis_eur_pro_l")
    assert liste["treffer_gesamt"] >= 5 and any(e["name"] == "mk_fraese" for e in liste["eintraege"])


async def test_frage_wie_berechnet_sich_mk_fraese(werkzeuge: dict[str, BaseTool]) -> None:
    # „Wie berechnet sich mk_fraese?"
    baum = await _art(werkzeuge, "erklaere_variable", name="mk_fraese")
    assert baum["methode"] == "formel"


# --- Part 2: the service maps a scripted agent stream to SSE + persists ----------------------- #
class _FakeSink:
    async def emit(self, event: Any) -> None:  # telemetry is empty in this test
        raise AssertionError("drain returned no events, so emit must not be called")


class _FakeSinks:
    usage = _FakeSink()
    execution_log = _FakeSink()


class _ScriptedAgent:
    """Stands in for KatalogChatAgent: replays a fixed tool call + result + answer token."""

    events: list[Any] = []

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def astream(self, messages: list[dict[str, Any]]) -> AsyncIterator[Any]:
        for event in _ScriptedAgent.events:
            yield event

    def drain_telemetry(self) -> tuple[list[Any], list[Any]]:
        return ([], [])


async def test_service_streams_tool_call_and_persists(
    katalog_engine: AsyncEngine, werkzeuge: dict[str, BaseTool], monkeypatch: Any
) -> None:
    artifact = await _art(werkzeuge, "finde_lieferanten_fuer_baustoff", baustoff_code="ASPHALT_AC22TS")
    _ScriptedAgent.events = [
        AgentToolCall(
            call_id="c1", name="finde_lieferanten_fuer_baustoff",
            arguments={"baustoff_code": "ASPHALT_AC22TS"},
        ),
        AgentToolResult(call_id="c1", name="finde_lieferanten_fuer_baustoff", payload=artifact),
        AgentToken(content="Diese Lieferanten können AC 22 T S liefern."),
    ]
    monkeypatch.setattr(
        "shared.services.katalog.chat_service.KatalogChatAgent", _ScriptedAgent
    )

    async with katalog_engine.begin() as conn:
        conversation = await ConversationRepository(conn).add(
            NewConversation(user_uuid=uuid4(), prompt_type=PromptType.KATALOG_CHAT, title="Katalog-Chat")
        )
    try:
        service = KatalogChatService(engine=katalog_engine, sinks=_FakeSinks())  # type: ignore[arg-type]
        events = [
            e
            async for e in service.run_turn(
                conversation, "Welche Lieferanten können AC 22 T S liefern?"
            )
        ]

        kinds = [e[EVENT] for e in events]
        assert EVENT_FUNCTION_CALL in kinds
        assert EVENT_TEXT_DELTA in kinds
        assert kinds[-1] == EVENT_DONE
        ergebnis = next(e for e in events if e[EVENT] == EVENT_FUNCTION_CALL_OUTPUT)
        assert ergebnis[DATA][DATA_RESULT]["lieferanten"]

        async with katalog_engine.connect() as conn:
            msgs = await MessageRepository(conn).list_for_conversation(conversation.conversation_uuid)
        assert any(m.kind == MessageKind.USER for m in msgs)
        assert "finde_lieferanten_fuer_baustoff" in {m.tool_name for m in msgs if m.tool_name}
        assert any(m.kind == MessageKind.ASSISTANT for m in msgs)
    finally:
        async with katalog_engine.begin() as conn:
            await ConversationRepository(conn).delete(conversation.conversation_uuid)
