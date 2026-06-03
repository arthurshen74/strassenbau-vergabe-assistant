"""The project-chat turn brain: a streaming ReAct agent over the project's documents and LV.

One `run_turn` drives a user -> assistant turn for a `project_chat` conversation and yields the same
SSE envelopes as the dispatcher, so the API streams it the same way. The latest user message is
appended to the conversation's user/assistant history and handed to a `ProjectChatAgent` (a LangChain
`create_agent` loop), which decides which tools to call -- project/LV retrieval, LV lookups, or
quantity aggregation -- and streams a grounded answer.

Messages are persisted in their own short transactions (the SSE response is long-lived and must not
hold one transaction open across the whole stream), mirroring the Dispatcher idiom; tool calls and
their results are persisted as function_call / function_call_output rows so the UI can render them
inline. The agent's answer-model telemetry is buffered during the run and drained to the usage /
execution-log sinks afterward (the sinks' engine is bound to the main loop).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.factory import TelemetrySinks
from shared.clients.llm.client import LLMClient
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind, PromptType
from shared.models.message import Message, NewMessage
from shared.models.prompt_version import PromptVersion
from shared.models.retrieval_request_schema import TurnRetrievalConfig
from shared.models.sse_schema import (
    DATA,
    DATA_ARGUMENTS,
    DATA_CALL_ID,
    DATA_CONTENT,
    DATA_ERRORS,
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
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.aggregate_lv import AggregateLVService
from shared.services.messages import CONTENT, ROLE, to_user_assistant_messages
from shared.services.project_chat_agent import (
    AgentToken,
    AgentToolCall,
    AgentToolResult,
    ProjectChatAgent,
)
from shared.services.prompt_runner import PromptVersionNotFoundError
from shared.services.retrieval import RetrievalConfig, RetrievalService

logger = logging.getLogger(__name__)


def config_from_request(dto: TurnRetrievalConfig | None) -> RetrievalConfig:
    """Map the request-side retrieval knobs to a service RetrievalConfig (sizes from settings)."""
    if dto is None:
        return RetrievalConfig()
    return RetrievalConfig(
        modality=dto.modality,
        multi_query=dto.multi_query,
        use_bm25=dto.use_bm25,
        use_cross_encoder=dto.use_cross_encoder,
    )


class ProjectChatService:
    def __init__(
        self,
        *,
        llm: LLMClient,
        engine: AsyncEngine,
        retrieval: RetrievalService,
        sinks: TelemetrySinks,
    ) -> None:
        self._llm = llm
        self._engine = engine
        self._retrieval = retrieval
        self._sinks = sinks

    async def run_turn(
        self, conversation: Conversation, user_content: str, config: RetrievalConfig
    ) -> AsyncIterator[dict[str, Any]]:
        conversation_id = conversation.conversation_uuid
        project_uuid = conversation.project_uuid
        assert project_uuid is not None  # project_chat conversations are always project-scoped

        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.USER,
                content=user_content,
            )
        )

        history = await self._load_history(conversation_id)
        messages = [
            {ROLE: m.role, CONTENT: m.content} for m in to_user_assistant_messages(history)
        ]
        prompt = await self._load_prompt()
        agent = ProjectChatAgent(
            project_uuid=project_uuid,
            config=config,
            engine=self._engine,
            retrieval=self._retrieval,
            aggregate=AggregateLVService(engine=self._engine, llm=self._llm),
            system_prompt=prompt.system_prompt,
            chat_model=prompt.model_name,
            temperature=prompt.temperature,
            prompt_type=PromptType.PROJECT_CHAT.value,
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
                    yield _function_call_output(event.call_id, event.name, True, event.payload)
        except Exception:
            logger.exception("project chat turn failed conversation=%s", conversation_id)
            yield _ui_notice("Bei der Beantwortung ist ein Fehler aufgetreten.")
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

    async def _emit_agent_telemetry(self, agent: ProjectChatAgent) -> None:
        usage_events, log_events = agent.drain_telemetry()
        for usage_event in usage_events:
            try:
                await self._sinks.usage.emit(usage_event)
            except Exception:
                logger.exception("failed to emit project-chat agent usage event")
        for log_event in log_events:
            try:
                await self._sinks.execution_log.emit(log_event)
            except Exception:
                logger.exception("failed to emit project-chat agent execution log")

    async def _load_prompt(self) -> PromptVersion:
        async with self._engine.connect() as conn:
            prompt = await PromptVersionRepository(conn).get_latest(PromptType.PROJECT_CHAT)
        if prompt is None:
            raise PromptVersionNotFoundError("no prompt version for type=project_chat")
        return prompt

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


def _ui_notice(content: str) -> dict[str, Any]:
    return {EVENT: EVENT_UI_NOTICE, DATA: {DATA_CONTENT: content}}


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
