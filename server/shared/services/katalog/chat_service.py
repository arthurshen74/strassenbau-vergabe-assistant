"""The katalog_chat turn brain: a streaming ReAct agent over the read-only Katalog
tools.

Mirrors `ProjectChatService` but for a global (non-project-scoped) catalog conversation:
one `run_turn` drives a user→assistant turn, appends the user message, hands the history
to a `KatalogChatAgent`, and relays the agent's tokens / tool calls / tool results as
the same SSE envelopes the dispatcher and project chat emit. Messages persist in their
own short transactions (the SSE response is long-lived and must not hold one transaction
open); tool calls and results persist as function_call / function_call_output rows so
the UI renders them inline. Agent telemetry is buffered during the run and drained to
the usage / execution-log sinks afterward.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.factory import TelemetrySinks
from shared.clients.tracing import flow_span
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind
from shared.models.message import Message, NewMessage
from shared.models.sse_schema import (
    DATA,
    DATA_ARGUMENTS,
    DATA_CALL_ID,
    DATA_CONTENT,
    DATA_ERRORS,
    DATA_LEVEL,
    DATA_NAME,
    DATA_RESULT,
    DATA_SUCCESS,
    DATA_TOOL_NAME,
    EVENT,
    EVENT_DONE,
    EVENT_FUNCTION_CALL,
    EVENT_FUNCTION_CALL_OUTPUT,
    EVENT_TEXT_DELTA,
    EVENT_UI_NOTICE,
    NOTICE_PROCESSING_ERROR,
    NoticeLevel,
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository
from shared.services.katalog.chat_agent import KatalogChatAgent
from shared.services.katalog.prompts import load_katalog_handbuch_prompt
from shared.services.messages import CONTENT, ROLE, to_user_assistant_messages
from shared.services.project_chat_agent import AgentToken, AgentToolCall

logger = logging.getLogger(__name__)


class KatalogChatService:
    def __init__(self, *, engine: AsyncEngine, sinks: TelemetrySinks) -> None:
        self._engine = engine
        self._sinks = sinks

    async def run_turn(
        self, conversation: Conversation, user_content: str
    ) -> AsyncIterator[dict[str, Any]]:
        # One root span per turn so the agent's LangChain spans and the sink spans
        # collapse into a single trace, grouped into the conversation's session.
        with flow_span(
            "katalog_chat.turn", session_id=str(conversation.conversation_uuid)
        ):
            async for event in self._run_turn(conversation, user_content):
                yield event

    async def _run_turn(
        self, conversation: Conversation, user_content: str
    ) -> AsyncIterator[dict[str, Any]]:
        conversation_id = conversation.conversation_uuid
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.USER,
                content=user_content,
            )
        )

        history = await self._load_history(conversation_id)
        messages = [
            {ROLE: m.role, CONTENT: m.content}
            for m in to_user_assistant_messages(history)
        ]
        # The Handbuch prompt owns the model choice (frontmatter) — load it per turn so
        # an edit in the prompt editor takes effect on the next turn without a restart.
        async with self._engine.connect() as conn:
            handbuch = await load_katalog_handbuch_prompt(conn)
        agent = KatalogChatAgent(
            engine=self._engine,
            system_prompt=handbuch.system_prompt,
            chat_model=handbuch.model_name,
            temperature=handbuch.temperature,
            conversation_uuid=conversation_id,
        )

        assistant_parts: list[str] = []
        try:
            async for event in agent.astream(messages):
                if isinstance(event, AgentToken):
                    assistant_parts.append(event.content)
                    yield _text_delta(event.content)
                elif isinstance(event, AgentToolCall):
                    await self._persist(
                        NewMessage(
                            conversation_uuid=conversation_id,
                            kind=MessageKind.FUNCTION_CALL,
                            call_id=event.call_id,
                            tool_name=event.name,
                            arguments=event.arguments,
                        )
                    )
                    yield _function_call(event.call_id, event.name, event.arguments)
                else:  # AgentToolResult
                    await self._persist(
                        NewMessage(
                            conversation_uuid=conversation_id,
                            kind=MessageKind.FUNCTION_CALL_OUTPUT,
                            call_id=event.call_id,
                            tool_name=event.name,
                            success=True,
                            data=event.payload,
                        )
                    )
                    yield _function_call_output(
                        event.call_id, event.name, True, event.payload
                    )
        except Exception:
            logger.exception(
                "katalog chat turn failed conversation=%s", conversation_id
            )
            yield _ui_notice(NOTICE_PROCESSING_ERROR, NoticeLevel.ERROR)
        finally:
            await self._emit_agent_telemetry(agent)

        assistant_text = "".join(assistant_parts)
        if assistant_text:
            await self._persist(
                NewMessage(
                    conversation_uuid=conversation_id,
                    kind=MessageKind.ASSISTANT,
                    content=assistant_text,
                )
            )
        await self._touch(conversation_id)
        yield {EVENT: EVENT_DONE, DATA: {}}

    async def _emit_agent_telemetry(self, agent: KatalogChatAgent) -> None:
        usage_events, log_events = agent.drain_telemetry()
        for usage_event in usage_events:
            try:
                await self._sinks.usage.emit(usage_event)
            except Exception:
                logger.exception("failed to emit katalog-chat agent usage event")
        for log_event in log_events:
            try:
                await self._sinks.execution_log.emit(log_event)
            except Exception:
                logger.exception("failed to emit katalog-chat agent execution log")

    async def _load_history(self, conversation_id: UUID) -> list[Message]:
        async with self._engine.connect() as conn:
            return await MessageRepository(conn).list_for_conversation(conversation_id)

    async def _persist(self, new: NewMessage) -> None:
        async with self._engine.begin() as conn:
            await MessageRepository(conn).add(new)

    async def _touch(self, conversation_id: UUID) -> None:
        async with self._engine.begin() as conn:
            await ConversationRepository(conn).touch(conversation_id)


def _text_delta(content: str) -> dict[str, Any]:
    return {EVENT: EVENT_TEXT_DELTA, DATA: {DATA_CONTENT: content}}


def _ui_notice(content: str, level: NoticeLevel = NoticeLevel.INFO) -> dict[str, Any]:
    return {EVENT: EVENT_UI_NOTICE, DATA: {DATA_CONTENT: content, DATA_LEVEL: level}}


def _function_call(
    call_id: str, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
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
