"""The project-chat turn brain: classify -> route -> stream a grounded answer.

One `run_turn` drives a user -> assistant turn for a `project_chat` conversation and yields the same
SSE envelopes as the dispatcher, so the API streams it the same way. The latest user message is
classified (CLASSIFY_PROJECT_CHAT_USER_MESSAGE -> ProjectChatRoute) and routed:

- lv_item_lookup / list_lv_items_by_parent_oz -> the LV item repository, surfaced as a tool result.
- rag_retrieval -> RetrievalService (SIMPLE/PLUS) or the LangChain agent (LANGCHAIN), then the
  project_chat answer prompt streamed token-by-token, grounded on the retrieved context.
- refuse -> a canned refusal.

Messages are persisted in their own short transactions (the SSE response is long-lived and must not
hold one transaction open across the whole stream), mirroring the Dispatcher idiom; the classifier
reads a user/assistant-only view of history so tool rows don't pollute routing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.factory import TelemetrySinks
from shared.clients.llm.client import LLMClient
from shared.clients.llm.events import TextDelta
from shared.models.chat_message import ChatMessage
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind, PromptType, RetrievalModality
from shared.models.llm_output_schemas import ProjectChatRoute
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
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.messages import MessageRepository
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.messages import CONTENT, ROLE, ROLE_USER, to_user_assistant_messages
from shared.services.prompt_runner import (
    PromptRunner,
    PromptVersionNotFoundError,
    render_template,
)
from shared.services.retrieval import RetrievalConfig, RetrievalError, RetrievalService
from shared.services.retrieval.langchain_agent import (
    LangchainRetriever,
    LangchainToken,
    LangchainToolCall,
    LangchainToolResult,
)
from shared.services.retrieval.service import VARIABLE_CONTEXT, format_context

logger = logging.getLogger(__name__)

ROLE_SYSTEM = "system"

# ProjectChatRoute.action values (must match shared.models.llm_output_schemas.project_chat_route).
ACTION_LV_ITEM_LOOKUP = "lv_item_lookup"
ACTION_LIST_LV_ITEMS = "list_lv_items_by_parent_oz"
ACTION_RAG_RETRIEVAL = "rag_retrieval"
ACTION_REFUSE = "refuse"

# Wire tool names for the synthesized tool rows; the UI (ToolResultMessage) renders LV results vs.
# retrieval sources by these names.
TOOL_LV_ITEM = "view_lvitem"
TOOL_LV_ITEMS = "view_lvitems"
TOOL_GET_CONTEXT = "get_context"

# Tool-result and tool-argument payload keys (the UI reads these out of `data`).
RESULT_LV_ITEM = "lv_item"
RESULT_LV_ITEMS = "lv_items"
RESULT_SOURCES = "sources"
ARG_OZ = "oz"
ARG_PARENT_OZ = "parent_oz"
ARG_QUERY = "query"

REFUSAL_TEXT = "Diese Frage lässt sich nicht aus den Unterlagen dieses Projekts beantworten."
MISSING_OZ_TEXT = "Es wurde keine gültige Ordnungszahl angegeben."


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

        assistant_parts: list[str] = []
        try:
            route = await self._classify(to_user_assistant_messages(history), project_uuid)
            async for event in self._route(route, conversation_id, project_uuid, config):
                if event[EVENT] == EVENT_TEXT_DELTA:
                    assistant_parts.append(event[DATA][DATA_CONTENT])
                yield event
        except Exception:
            logger.exception("project chat turn failed conversation=%s", conversation_id)
            yield _ui_notice("Bei der Beantwortung ist ein Fehler aufgetreten.")

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

    async def _route(
        self,
        route: ProjectChatRoute,
        conversation_id: UUID,
        project_uuid: UUID,
        config: RetrievalConfig,
    ) -> AsyncIterator[dict[str, Any]]:
        if route.action == ACTION_LV_ITEM_LOOKUP:
            async for event in self._lv_item_lookup(conversation_id, project_uuid, route.oz):
                yield event
        elif route.action == ACTION_LIST_LV_ITEMS:
            async for event in self._lv_items_list(
                conversation_id, project_uuid, route.parent_oz
            ):
                yield event
        elif route.action == ACTION_RAG_RETRIEVAL:
            async for event in self._rag(conversation_id, project_uuid, route, config):
                yield event
        else:  # refuse, or any unexpected action
            yield _text_delta(REFUSAL_TEXT)

    async def _lv_item_lookup(
        self, conversation_id: UUID, project_uuid: UUID, oz: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        if not oz:
            yield _text_delta(MISSING_OZ_TEXT)
            return
        async with self._engine.connect() as conn:
            item = await LVItemRepository(conn).get_by_project_and_oz(project_uuid, oz)
        data = {RESULT_LV_ITEM: item.model_dump(mode="json") if item else None}
        for event in await self._tool_pair(
            conversation_id, TOOL_LV_ITEM, {ARG_OZ: oz}, item is not None, data
        ):
            yield event
        if item is None:
            yield _text_delta(f"Zur Ordnungszahl {oz} wurde keine Position gefunden.")
        else:
            yield _text_delta(f"Position {item.oz}: {item.kurztext}")

    async def _lv_items_list(
        self, conversation_id: UUID, project_uuid: UUID, parent_oz: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        if not parent_oz:
            yield _text_delta(MISSING_OZ_TEXT)
            return
        async with self._engine.connect() as conn:
            items = await LVItemRepository(conn).list_by_parent_oz(project_uuid, parent_oz)
        data = {RESULT_LV_ITEMS: [i.model_dump(mode="json") for i in items]}
        for event in await self._tool_pair(
            conversation_id, TOOL_LV_ITEMS, {ARG_PARENT_OZ: parent_oz}, True, data
        ):
            yield event
        if items:
            yield _text_delta(f"{len(items)} Positionen unter {parent_oz} gefunden.")
        else:
            yield _text_delta(f"Unter {parent_oz} wurden keine Positionen gefunden.")

    async def _rag(
        self,
        conversation_id: UUID,
        project_uuid: UUID,
        route: ProjectChatRoute,
        config: RetrievalConfig,
    ) -> AsyncIterator[dict[str, Any]]:
        query = route.search_query or ""
        if not query:
            yield _text_delta(REFUSAL_TEXT)
            return
        if config.modality is RetrievalModality.LANGCHAIN:
            async for event in self._rag_langchain(conversation_id, project_uuid, query):
                yield event
        else:
            async for event in self._rag_simple_plus(
                conversation_id, project_uuid, query, config
            ):
                yield event

    async def _rag_simple_plus(
        self,
        conversation_id: UUID,
        project_uuid: UUID,
        query: str,
        config: RetrievalConfig,
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            ctx = await self._retrieval.retrieve_context(query, project_uuid, config)
        except RetrievalError as exc:
            # PLUS needs an LV document; fall back to SIMPLE rather than failing the turn.
            yield _ui_notice(f"{exc}; weiche auf einfache Suche aus.")
            fallback = config.model_copy(update={"modality": RetrievalModality.SIMPLE})
            ctx = await self._retrieval.retrieve_context(query, project_uuid, fallback)

        for event in await self._tool_pair(
            conversation_id, TOOL_GET_CONTEXT, {ARG_QUERY: query}, True, ctx.model_dump(mode="json")
        ):
            yield event

        prompt = await self._load_prompt()
        system = render_template(
            prompt.system_prompt, {VARIABLE_CONTEXT: format_context(ctx.context)}
        )
        messages: list[dict[str, Any]] = [
            {ROLE: ROLE_SYSTEM, CONTENT: system},
            {ROLE: ROLE_USER, CONTENT: query},
        ]
        async for event in self._llm.stream_chat(
            model=prompt.model_name,
            messages=messages,
            temperature=prompt.temperature,
            top_p=prompt.top_p,
            chat_prompt_type=PromptType.PROJECT_CHAT.value,
            chat_prompt_version=prompt.version,
            project_uuid=project_uuid,
        ):
            if isinstance(event, TextDelta):
                yield _text_delta(event.content)

    async def _rag_langchain(
        self, conversation_id: UUID, project_uuid: UUID, query: str
    ) -> AsyncIterator[dict[str, Any]]:
        prompt = await self._load_prompt()
        retriever = LangchainRetriever(
            project_uuid=project_uuid,
            chat_model=prompt.model_name,
            temperature=prompt.temperature,
            system_prompt=prompt.system_prompt,
            prompt_type=PromptType.PROJECT_CHAT.value,
        )
        call_id: str | None = None
        try:
            async for event in retriever.astream(query):
                if isinstance(event, LangchainToken):
                    yield _text_delta(event.content)
                elif isinstance(event, LangchainToolCall):
                    call_id = str(uuid4())
                    await self._persist(
                        NewMessage(
                            conversation_uuid=conversation_id,
                            kind=MessageKind.FUNCTION_CALL,
                            call_id=call_id,
                            tool_name=TOOL_GET_CONTEXT,
                            arguments={ARG_QUERY: event.query},
                        )
                    )
                    yield _function_call(call_id, TOOL_GET_CONTEXT, {ARG_QUERY: event.query})
                elif isinstance(event, LangchainToolResult):
                    pair_id = call_id or str(uuid4())
                    data = {RESULT_SOURCES: [s.model_dump(mode="json") for s in event.sources]}
                    await self._persist(
                        NewMessage(
                            conversation_uuid=conversation_id,
                            kind=MessageKind.FUNCTION_CALL_OUTPUT,
                            call_id=pair_id,
                            tool_name=TOOL_GET_CONTEXT,
                            success=True,
                            data=data,
                        )
                    )
                    yield _function_call_output(pair_id, TOOL_GET_CONTEXT, True, data)
                    call_id = None
        finally:
            await self._emit_langchain_telemetry(retriever)
            retriever.close()

    async def _classify(
        self, messages: Sequence[ChatMessage], project_uuid: UUID
    ) -> ProjectChatRoute:
        async with self._engine.connect() as conn:
            runner = PromptRunner(PromptVersionRepository(conn), self._llm)
            return await runner.classify_project_chat(messages, project_uuid=project_uuid)

    async def _tool_pair(
        self,
        conversation_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Persist + render a function_call/function_call_output pair for a completed step."""
        call_id = str(uuid4())
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
            )
        )
        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.FUNCTION_CALL_OUTPUT,
                call_id=call_id,
                tool_name=tool_name,
                success=success,
                data=data,
            )
        )
        return [
            _function_call(call_id, tool_name, arguments),
            _function_call_output(call_id, tool_name, success, data),
        ]

    async def _emit_langchain_telemetry(self, retriever: LangchainRetriever) -> None:
        usage_events, log_events = retriever.drain_telemetry()
        for usage_event in usage_events:
            try:
                await self._sinks.usage.emit(usage_event)
            except Exception:
                logger.exception("failed to emit langchain usage event")
        for log_event in log_events:
            try:
                await self._sinks.execution_log.emit(log_event)
            except Exception:
                logger.exception("failed to emit langchain execution log")

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
