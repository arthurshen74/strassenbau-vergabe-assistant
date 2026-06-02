"""Generic streaming dispatcher loop, reused by every tool-calling chat.

`run_turn` drives one user -> assistant turn and yields SSE event payloads. The conversation's
`prompt_type` selects the system prompt and the tool catalog, so the same loop serves the main
dispatcher and project chat. Tools execute via direct service calls (a `UnitOfWork` on a short
read connection). Messages are persisted in their own short transactions because the SSE
response is long-lived and must not hold one transaction open across the whole stream.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.clients.llm.events import Done, TextDelta, ToolCall, ToolCallsReady
from shared.db.unit_of_work import UnitOfWork
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind
from shared.models.message import Message, NewMessage
from shared.models.prompt_version import PromptVersion
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
from shared.services.messages import (
    CONTENT,
    ROLE,
    assistant_tool_calls_message,
    tool_call_entry,
    tool_reply_message,
    tool_result_payload,
    to_chat_completions_messages,
)
from shared.services.prompt_runner import PromptVersionNotFoundError
from shared.tools import ToolContext, catalog_for, tool_by_name

logger = logging.getLogger(__name__)

# Cap the tool-call <-> model-response loop so a misbehaving model can't stream forever.
_MAX_TOOL_TURNS = 8

ROLE_SYSTEM = "system"

# A resolved tool call: the call plus its execution result.
_ToolResult = tuple[ToolCall, bool, dict[str, Any] | None, list[str] | None]


class Dispatcher:
    def __init__(self, llm: LLMClient, engine: AsyncEngine) -> None:
        self._llm = llm
        self._engine = engine

    async def run_turn(
        self, conversation: Conversation, user_content: str
    ) -> AsyncIterator[dict[str, Any]]:
        conversation_id = conversation.conversation_uuid
        prompt_type = conversation.prompt_type

        await self._persist(
            NewMessage(
                conversation_uuid=conversation_id,
                kind=MessageKind.USER,
                content=user_content,
            )
        )

        prompt = await self._load_prompt(conversation)
        history = await self._load_history(conversation_id)
        chat_messages: list[dict[str, Any]] = [
            {ROLE: ROLE_SYSTEM, CONTENT: prompt.system_prompt},
            *to_chat_completions_messages(history),
        ]
        tools = [t.to_openai_tool() for t in catalog_for(prompt_type)]

        accumulated_text = ""
        hit_cap = True
        for _turn in range(_MAX_TOOL_TURNS):
            text_parts: list[str] = []
            turn_tool_calls: list[ToolCall] = []
            async for event in self._llm.stream_chat(
                model=prompt.model_name,
                messages=chat_messages,
                tools=tools or None,
                temperature=prompt.temperature,
                top_p=prompt.top_p,
                chat_prompt_type=prompt_type.value,
                chat_prompt_version=prompt.version,
                project_uuid=conversation.project_uuid,
            ):
                if isinstance(event, TextDelta):
                    text_parts.append(event.content)
                    yield {EVENT: EVENT_TEXT_DELTA, DATA: {DATA_CONTENT: event.content}}
                elif isinstance(event, ToolCallsReady):
                    turn_tool_calls = event.tool_calls
                elif isinstance(event, Done):
                    pass

            if not turn_tool_calls:
                accumulated_text = "".join(text_parts)
                hit_cap = False
                break

            results: list[_ToolResult] = []
            for call in turn_tool_calls:
                args = _parse_args(call.arguments)
                await self._persist(
                    NewMessage(
                        conversation_uuid=conversation_id,
                        kind=MessageKind.FUNCTION_CALL,
                        call_id=call.id,
                        tool_name=call.name,
                        arguments=args,
                    )
                )
                yield {
                    EVENT: EVENT_FUNCTION_CALL,
                    DATA: {DATA_CALL_ID: call.id, DATA_NAME: call.name, DATA_ARGUMENTS: args},
                }

                success, data, errors = await self._execute(conversation, call.name, args)
                await self._persist(
                    NewMessage(
                        conversation_uuid=conversation_id,
                        kind=MessageKind.FUNCTION_CALL_OUTPUT,
                        call_id=call.id,
                        tool_name=call.name,
                        success=success,
                        data=data,
                        errors=errors,
                    )
                )
                yield {
                    EVENT: EVENT_FUNCTION_CALL_OUTPUT,
                    DATA: {
                        DATA_CALL_ID: call.id,
                        DATA_TOOL_NAME: call.name,
                        DATA_SUCCESS: success,
                        DATA_RESULT: data,
                        DATA_ERRORS: errors,
                    },
                }
                results.append((call, success, data, errors))

            # Extend the wire history: one assistant tool_calls envelope, then the replies.
            chat_messages.append(
                assistant_tool_calls_message(
                    [tool_call_entry(c.id, c.name, c.arguments) for c, _, _, _ in results]
                )
            )
            for call, success, data, errors in results:
                chat_messages.append(
                    tool_reply_message(call.id, tool_result_payload(success, data, errors))
                )

        if hit_cap:
            logger.warning("dispatcher tool-turn cap hit conversation=%s", conversation_id)
            yield {
                EVENT: EVENT_UI_NOTICE,
                DATA: {DATA_CONTENT: "Reached tool-call limit; finishing without further actions."},
            }

        if accumulated_text:
            await self._persist(
                NewMessage(
                    conversation_uuid=conversation_id,
                    kind=MessageKind.ASSISTANT,
                    content=accumulated_text,
                )
            )
        await self._touch(conversation_id)
        yield {EVENT: EVENT_DONE, DATA: {}}

    async def _execute(
        self, conversation: Conversation, name: str, args: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None, list[str] | None]:
        tool = tool_by_name(conversation.prompt_type, name)
        if tool is None:
            return False, None, [f"Unknown tool: {name}"]
        try:
            validated = tool.input_model.model_validate(args)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return False, None, errors
        try:
            async with self._engine.connect() as conn:
                ctx = ToolContext(uow=UnitOfWork(conn), project_uuid=conversation.project_uuid)
                data = await tool.handler(validated, ctx)
            return True, data, None
        except Exception as exc:
            logger.exception("tool execution failed name=%s", name)
            return False, None, [f"Tool execution failed: {exc}"]

    async def _load_prompt(self, conversation: Conversation) -> PromptVersion:
        async with self._engine.connect() as conn:
            pv = await PromptVersionRepository(conn).get_latest(conversation.prompt_type)
        if pv is None:
            raise PromptVersionNotFoundError(
                f"no prompt version for type={conversation.prompt_type.value}"
            )
        return pv

    async def _load_history(self, conversation_id: UUID) -> list[Message]:
        async with self._engine.connect() as conn:
            return await MessageRepository(conn).list_for_conversation(conversation_id)

    async def _persist(self, new: NewMessage) -> None:
        async with self._engine.begin() as conn:
            await MessageRepository(conn).add(new)

    async def _touch(self, conversation_id: UUID) -> None:
        async with self._engine.begin() as conn:
            await ConversationRepository(conn).touch(conversation_id)


def _parse_args(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
