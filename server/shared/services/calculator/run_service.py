"""Drives one EKT calculator run as a conversation, streamed to the UI over SSE.

A run is a sequence of SSE segments glued by the LangGraph Postgres checkpointer
(`thread_id = conversation_uuid`): `start` streams until the first HITL interrupt (or the
end), `resume` continues from the checkpoint with the Kalkulator's decision. Each segment
maps the graph's `reasoning_log` to `text_delta` events and persists them as assistant
messages (the `ProjectChatService` idiom: short transactions, never one held open across the
stream), surfaces an interrupt as an `interrupt` event + a persisted prompt, and emits the
final EKT row + Nachweistabelle as a `function_call_output`. `calculation_status` tracks the lifecycle so
the API knows whether a turn is a resume (awaiting_input) or a follow-up chat (complete).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.clients.tracing import flow_span
from shared.config import settings
from shared.models.conversation import Conversation
from shared.models.enums import CalculationStatus, MessageKind, PromptType
from shared.models.lv_item import LVItem
from shared.models.message import NewMessage
from shared.models.prompt_version import PromptVersion
from shared.models.sse_schema import (
    DATA,
    DATA_ARGUMENTS,
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
from shared.services.calculator.graph import (
    CALCULATOR_RETRIEVAL_CONFIG,
    REASONING_LLM,
    REASONING_PROVIDER,
    ContextRetriever,
    build_graph,
)
from shared.services.calculator.prompts import load_calculator_prompts
from shared.services.messages import (
    CONTENT,
    ROLE,
    to_user_assistant_messages,
)
from shared.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

# astream(stream_mode="updates") signals a HITL pause under this key.
INTERRUPT_KEY = "__interrupt__"

# tool_name discriminators for the calculator's synthetic transcript rows.
TOOL_INTERRUPT = "interrupt"
TOOL_EKT_RESULT = "ekt_result"


class CalculatorRunService:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        llm: LLMClient,
        retrieval: RetrievalService,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self._engine = engine
        self._llm = llm
        self._retrieval = retrieval
        self._checkpointer = checkpointer

    async def start(
        self, conversation: Conversation, item: LVItem
    ) -> AsyncIterator[dict[str, Any]]:
        """Begin a run for one LV position; stream until the first interrupt or completion.

        A run reuses `thread_id = conversation_uuid`, so a re-calculation (the Kalkulator asks
        to recalculate, e.g. with a different value) must start from a clean checkpoint —
        otherwise the prior run's reducer channels (reasoning_log, warnungen) accumulate and the
        finished END state blocks a fresh start. We wipe the thread first; it is a no-op on the
        first run, and safe because a mid-run conversation is 409-guarded against a new start."""
        await self._checkpointer.adelete_thread(str(conversation.conversation_uuid))
        prompts = await self._load_prompts()
        payload = {
            "position": _position(item),
            "project_uuid": conversation.project_uuid,
            "conversation_uuid": conversation.conversation_uuid,
            "chat_verlauf": await self._chat_transcript(conversation),
            "vorgaben": {},
        }
        async for event in self._run_segment(conversation, payload, prompts):
            yield event

    async def _load_prompts(self) -> dict[PromptType, PromptVersion]:
        """Resolve the calculator's DB-backed prompt versions once per run segment. Mock runs skip
        the LLM sites entirely, so they need no prompts (and none may be seeded)."""
        if settings.calculator_mock:
            return {}
        async with self._engine.connect() as conn:
            return await load_calculator_prompts(conn)

    async def _chat_transcript(self, conversation: Conversation) -> list[dict[str, Any]]:
        """The pre-launch user/assistant transcript (precedence source 0). The graph's
        extract_chat_values node harvests the values the Kalkulator already stated from it."""
        async with self._engine.connect() as conn:
            history = await MessageRepository(conn).list_for_conversation(
                conversation.conversation_uuid
            )
        return [
            {ROLE: m.role, CONTENT: m.content} for m in to_user_assistant_messages(history)
        ]

    async def resume(
        self, conversation: Conversation, decision: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Continue a paused run from its checkpoint with the Kalkulator's decision."""
        prompts = await self._load_prompts()
        async for event in self._run_segment(
            conversation, Command(resume=decision), prompts
        ):
            yield event

    def _app(
        self,
        project_uuid: UUID,
        conversation_uuid: UUID,
        prompts: Mapping[PromptType, PromptVersion],
    ):
        return build_graph(
            retriever=self._retriever(project_uuid, conversation_uuid),
            llm=self._llm,
            prompts=prompts,
            checkpointer=self._checkpointer,
        )

    def _retriever(self, project_uuid: UUID, conversation_uuid: UUID) -> ContextRetriever:
        async def retrieve(query: str) -> list[str]:
            ctx = await self._retrieval.retrieve_context(
                query,
                project_uuid,
                CALCULATOR_RETRIEVAL_CONFIG,
                conversation_uuid=conversation_uuid,
            )
            return [c.chunk_text for c in ctx.context]

        return retrieve

    async def _run_segment(
        self,
        conversation: Conversation,
        payload: Any,
        prompts: Mapping[PromptType, PromptVersion],
    ) -> AsyncIterator[dict[str, Any]]:
        # One root span per streamed segment (the start, and each resume after a HITL gate) so the
        # LangGraph node spans, native ES query spans, and LLMClient sink spans collapse into one
        # trace; session.id groups every segment of a run into one Phoenix session.
        assert conversation.project_uuid is not None  # ekt_calculator runs are project-scoped
        with flow_span(
            "ekt.calculation",
            session_id=str(conversation.conversation_uuid),
            attributes={"project.uuid": str(conversation.project_uuid)},
        ):
            async for event in self._stream_segment(conversation, payload, prompts):
                yield event

    async def _stream_segment(
        self,
        conversation: Conversation,
        payload: Any,
        prompts: Mapping[PromptType, PromptVersion],
    ) -> AsyncIterator[dict[str, Any]]:
        conversation_id = conversation.conversation_uuid
        assert conversation.project_uuid is not None  # ekt_calculator runs are project-scoped
        app = self._app(conversation.project_uuid, conversation_id, prompts)
        config = {"configurable": {"thread_id": str(conversation_id)}}

        await self._set_status(conversation_id, CalculationStatus.RUNNING)
        _trace(conversation_id, "--- streaming calculation segment ---")
        interrupted = False
        # Diagnostic counters: distinguish "graph never streamed reasoning" (custom writer broken)
        # from "graph streamed fine but the client/transport dropped it". Traced at segment end.
        started_at = time.monotonic()
        custom_count = 0
        update_count = 0
        try:
            # "custom" carries each reasoning entry live as a node produces it (so the long
            # per-driver node streams incrementally); "updates" carries completed-node output for
            # persistence and the HITL interrupt signal.
            async for mode, chunk in app.astream(
                payload, config, stream_mode=["updates", "custom"]
            ):
                if mode == "custom":
                    custom_count += 1
                    if custom_count == 1:
                        _trace(
                            conversation_id,
                            f"first reasoning delta after {time.monotonic() - started_at:.2f}s",
                        )
                    text = _format_reasoning(chunk)
                    _trace(conversation_id, text.rstrip("\n"))
                    yield _text_delta(text)
                    continue
                update_count += 1
                if INTERRUPT_KEY in chunk:
                    value = chunk[INTERRUPT_KEY][0].value
                    _trace(conversation_id, f"PAUSED ({value.get('stage')}); awaiting input")
                    await self._persist_interrupt(conversation_id, value)
                    yield _interrupt_event(value)
                    interrupted = True
                    continue
                for node_output in chunk.values():
                    outputs = node_output if isinstance(node_output, list) else [node_output]
                    for output in outputs:
                        if isinstance(output, dict):
                            await self._persist_reasoning(conversation_id, output)
        except Exception:
            logger.exception("calculator run failed conversation=%s", conversation_id)
            _trace(conversation_id, "run FAILED (see server logs)")
            await self._set_status(conversation_id, CalculationStatus.FAILED)
            yield _ui_notice(NOTICE_PROCESSING_ERROR, NoticeLevel.ERROR)
            yield {EVENT: EVENT_DONE, DATA: {}}
            return

        _trace(
            conversation_id,
            f"segment stats: {custom_count} reasoning deltas, {update_count} node updates",
        )
        if custom_count == 0 and update_count > 0:
            _trace(
                conversation_id,
                "WARNING: nodes produced output but streamed 0 reasoning deltas -- the custom "
                "writer is inactive (see graph._write_live); the UI will look stuck until the result.",
            )

        if interrupted:
            await self._set_status(conversation_id, CalculationStatus.AWAITING_INPUT)
        else:
            async for event in self._emit_result(app, config, conversation_id):
                yield event
            await self._set_status(conversation_id, CalculationStatus.COMPLETE)
            _trace(conversation_id, "run complete")
        await self._touch(conversation_id)
        yield {EVENT: EVENT_DONE, DATA: {}}

    async def _persist_reasoning(self, conversation_id: UUID, output: dict[str, Any]) -> None:
        """Persist a completed node's reasoning_log as one assistant message. The lines already
        streamed live via the custom events; this is the authoritative copy for the transcript."""
        entries = output.get("reasoning_log") or []
        if not entries:
            return
        content = "".join(_format_reasoning(entry) for entry in entries)
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.ASSISTANT,
                content=content,
            )
        )

    async def _emit_result(
        self, app: Any, config: dict[str, Any], conversation_id: UUID
    ) -> AsyncIterator[dict[str, Any]]:
        state = (await app.aget_state(config)).values
        if state.get("abgebrochen"):
            yield _ui_notice("Kalkulation abgebrochen.", NoticeLevel.INFO)
            return
        data = {
            "ekt_zeile": state.get("ekt_zeile"),
            "nachweis_tabelle": state.get("nachweis_tabelle", []),
            "beschreibung": state.get("beschreibung"),
            "warnungen": state.get("warnungen", []),
        }
        call_id = uuid4().hex
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL,
                call_id=call_id,
                tool_name=TOOL_EKT_RESULT,
                arguments={},
            )
        )
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL_OUTPUT,
                call_id=call_id,
                tool_name=TOOL_EKT_RESULT,
                success=True,
                data=data,
            )
        )
        yield _function_call(call_id, TOOL_EKT_RESULT, {})
        yield _function_call_output(call_id, TOOL_EKT_RESULT, True, data)

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


def _position(item: LVItem) -> dict[str, Any]:
    return {
        "oz": item.oz,
        "kurztext": item.kurztext,
        "langtext": item.langtext_resolved or item.langtext,
        "hinweis": item.hinweis,
        "menge": str(item.menge),
        "einheit": item.einheit,
        "baustoff_code": None,
    }


def _format_reasoning(entry: dict[str, Any]) -> str:
    kind = entry["kind"]
    text = entry["text"]
    if kind == REASONING_LLM:
        return f"  - {text}\n"
    if kind == REASONING_PROVIDER:
        return f"  (model) {text}\n"
    return f"{text}\n"


def _trace(conversation_id: UUID, text: str) -> None:
    # Operator-facing mirror of the SSE stream: lets a run be followed in `docker compose logs api`
    # at the same time as the UI. Printed (not logged) so it shows regardless of log-level config.
    print(f"[ekt {str(conversation_id)[:8]}] {text}", flush=True)


def _text_delta(content: str) -> dict[str, Any]:
    return {EVENT: EVENT_TEXT_DELTA, DATA: {DATA_CONTENT: content}}


def _ui_notice(content: str, level: NoticeLevel) -> dict[str, Any]:
    return {EVENT: EVENT_UI_NOTICE, DATA: {DATA_CONTENT: content, DATA_LEVEL: level}}


def _interrupt_event(value: dict[str, Any]) -> dict[str, Any]:
    return {EVENT: EVENT_INTERRUPT, DATA: {DATA_STAGE: value.get("stage"), DATA_PAYLOAD: value}}


def _function_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        EVENT: EVENT_FUNCTION_CALL,
        DATA: {DATA_CALL_ID: call_id, DATA_NAME: name, DATA_ARGUMENTS: arguments},
    }


def _function_call_output(
    call_id: str, tool_name: str, success: bool, data: dict[str, Any]
) -> dict[str, Any]:
    return {
        EVENT: EVENT_FUNCTION_CALL_OUTPUT,
        DATA: {
            DATA_CALL_ID: call_id,
            DATA_TOOL_NAME: tool_name,
            DATA_SUCCESS: success,
            DATA_RESULT: data,
            DATA_ERRORS: None,
        },
    }
