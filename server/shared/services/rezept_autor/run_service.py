"""Drives one recipe-author run as a conversation, streamed to the UI over SSE.

Mirrors the calculator's wiring (`services/calculator/run_service.py`): `thread_id =
conversation_uuid` glues the segments through the LangGraph Postgres checkpointer; `start` streams
the describe→validate→review segment until the interrupt, `resume` continues from the checkpoint with
the reviewer's decision. Reasoning is streamed as `text_delta` events and persisted as one assistant
message per segment; the interrupt surfaces as an `interrupt` event; the final outcome (draft saved /
activated / discarded) is a `function_call_output`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import (
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
    ROLE_SYSTEM,
    ROLE_USER,
    LLMClient,
)
from shared.config import settings
from shared.models.conversation import Conversation
from shared.models.enums import CalculationStatus, MessageKind
from shared.models.katalog import KatalogBundle
from shared.models.message import NewMessage
from shared.models.sse_schema import (
    DATA,
    DATA_CALL_ID,
    DATA_CONTENT,
    DATA_ERRORS,
    DATA_LEVEL,
    DATA_NAME,
    DATA_PAYLOAD,
    DATA_RESULT,
    DATA_STAGE,
    DATA_SUCCESS,
    DATA_TOOL_NAME,
    EVENT,
    EVENT_CALC_START,
    EVENT_DONE,
    EVENT_FUNCTION_CALL,
    EVENT_FUNCTION_CALL_OUTPUT,
    EVENT_INTERRUPT,
    EVENT_TEXT_DELTA,
    EVENT_UI_NOTICE,
    NOTICE_PROCESSING_ERROR,
    NoticeLevel,
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository
from shared.services.katalog.service import KatalogService
from shared.services.rezept_autor.graph import build_graph
from shared.services.rezept_autor.prompts import REZEPT_AUTOR_SYSTEM, baue_user_prompt

logger = logging.getLogger(__name__)

INTERRUPT_KEY = "__interrupt__"
TOOL_INTERRUPT = "interrupt"
TOOL_REZEPT_RESULT = "rezept_result"
# Reuses the calculator's reasoning marker so the UI collapses the block the same way.
CALC_REASONING_MARKER = "calc_reasoning"
DEFAULT_AUTOR = "kalkulator"


class RezeptAutorRunService:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        llm: LLMClient,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self._engine = engine
        self._llm = llm
        self._checkpointer = checkpointer
        self._katalog = KatalogService(engine)

    async def start(
        self, conversation: Conversation, beschreibung: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Begin a run from a natural-language recipe description; stream until the review interrupt."""
        await self._checkpointer.adelete_thread(str(conversation.conversation_uuid))
        async for event in self._stream_segment(conversation, {"beschreibung": beschreibung}):
            yield event

    async def resume(
        self, conversation: Conversation, decision: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Continue a paused run with the reviewer's decision (feedback / confirm / discard)."""
        async for event in self._stream_segment(conversation, Command(resume=decision)):
            yield event

    def _app(self, conversation: Conversation):
        return build_graph(
            entwerfer=self._entwerfer(conversation),
            pruefer=self._katalog.pruefen,
            speichern=lambda bundle: self._katalog.entwurf_speichern(bundle, benutzer=DEFAULT_AUTOR),
            aktivieren=self._katalog.bundle_aktivieren,
            checkpointer=self._checkpointer,
        )

    def _entwerfer(self, conversation: Conversation):
        async def entwerfer(beschreibung: str, fehler: list[str], feedback: str | None) -> KatalogBundle:
            bundle, _reasoning = await self._llm.chat_with_reasoning(
                model=settings.calculator_model,
                messages=[
                    {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: REZEPT_AUTOR_SYSTEM},
                    {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: baue_user_prompt(beschreibung, fehler, feedback)},
                ],
                output_model=KatalogBundle,
                reasoning_effort=settings.calculator_reasoning_effort,
                strict=False,
                conversation_uuid=conversation.conversation_uuid,
            )
            return bundle

        return entwerfer

    async def _stream_segment(
        self, conversation: Conversation, payload: Any
    ) -> AsyncIterator[dict[str, Any]]:
        conversation_id = conversation.conversation_uuid
        app = self._app(conversation)
        config = {"configurable": {"thread_id": str(conversation_id)}}

        await self._set_status(conversation_id, CalculationStatus.RUNNING)
        yield {EVENT: EVENT_CALC_START, DATA: {}}
        interrupted = False
        reasoning_parts: list[str] = []
        try:
            async for chunk in app.astream(payload, config, stream_mode="updates"):
                if INTERRUPT_KEY in chunk:
                    value = chunk[INTERRUPT_KEY][0].value
                    await self._persist_interrupt(conversation_id, value)
                    yield {EVENT: EVENT_INTERRUPT, DATA: {DATA_STAGE: value.get("stage"), DATA_PAYLOAD: value}}
                    interrupted = True
                    continue
                for node_output in chunk.values():
                    if isinstance(node_output, dict):
                        for entry in node_output.get("reasoning_log") or []:
                            text = f"{entry['text']}\n"
                            reasoning_parts.append(text)
                            yield {EVENT: EVENT_TEXT_DELTA, DATA: {DATA_CONTENT: text}}
        except Exception:
            logger.exception("rezept_autor run failed conversation=%s", conversation_id)
            await self._persist_reasoning_block(conversation_id, reasoning_parts)
            await self._set_status(conversation_id, CalculationStatus.FAILED)
            yield {EVENT: EVENT_UI_NOTICE, DATA: {DATA_CONTENT: NOTICE_PROCESSING_ERROR, DATA_LEVEL: NoticeLevel.ERROR}}
            yield {EVENT: EVENT_DONE, DATA: {}}
            return

        await self._persist_reasoning_block(conversation_id, reasoning_parts)
        if interrupted:
            await self._set_status(conversation_id, CalculationStatus.AWAITING_INPUT)
        else:
            async for event in self._emit_result(app, config, conversation_id):
                yield event
            await self._set_status(conversation_id, CalculationStatus.COMPLETE)
        await self._touch(conversation_id)
        yield {EVENT: EVENT_DONE, DATA: {}}

    async def _emit_result(
        self, app: Any, config: dict[str, Any], conversation_id: UUID
    ) -> AsyncIterator[dict[str, Any]]:
        state = (await app.aget_state(config)).values
        data = {
            "bundle": state.get("bundle"),
            "bericht": state.get("bericht"),
            "gespeichert": bool(state.get("gespeichert")),
            "aktiviert": bool(state.get("aktiviert")),
            "verworfen": bool(state.get("verworfen")),
            "bundle_uuid": state.get("bundle_uuid"),
        }
        call_id = uuid4().hex
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL,
                call_id=call_id,
                tool_name=TOOL_REZEPT_RESULT,
                arguments={},
            )
        )
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL_OUTPUT,
                call_id=call_id,
                tool_name=TOOL_REZEPT_RESULT,
                success=True,
                data=data,
            )
        )
        yield {EVENT: EVENT_FUNCTION_CALL, DATA: {DATA_CALL_ID: call_id, DATA_NAME: TOOL_REZEPT_RESULT, "arguments": {}}}
        yield {
            EVENT: EVENT_FUNCTION_CALL_OUTPUT,
            DATA: {
                DATA_CALL_ID: call_id,
                DATA_TOOL_NAME: TOOL_REZEPT_RESULT,
                DATA_SUCCESS: True,
                DATA_RESULT: data,
                DATA_ERRORS: None,
            },
        }

    async def _persist_reasoning_block(self, conversation_id: UUID, parts: list[str]) -> None:
        content = "".join(p for p in parts if p)
        if not content:
            return
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.ASSISTANT,
                content=content,
                data={CALC_REASONING_MARKER: True},
            )
        )

    async def _persist_interrupt(self, conversation_id: UUID, value: dict[str, Any]) -> None:
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL,
                call_id=uuid4().hex,
                tool_name=TOOL_INTERRUPT,
                arguments=value,
            )
        )

    async def _persist(self, new: NewMessage) -> None:
        async with self._engine.begin() as conn:
            await MessageRepository(conn).add(new)

    async def _set_status(self, conversation_id: UUID, status: CalculationStatus) -> None:
        async with self._engine.begin() as conn:
            await ConversationRepository(conn).set_calculation_status(conversation_id, status)

    async def _touch(self, conversation_id: UUID) -> None:
        async with self._engine.begin() as conn:
            await ConversationRepository(conn).touch(conversation_id)
