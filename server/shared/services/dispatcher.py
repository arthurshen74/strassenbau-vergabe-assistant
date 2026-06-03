"""Single-shot dispatcher loop for the main command bar.

`dispatch` drives one stateless user message: it loads the DISPATCHER prompt + tool catalog, runs the
tool-calling loop, and yields SSE event payloads (the same envelopes the project chat yields, so the
API streams it identically). The dispatcher keeps no conversation history and persists nothing -- it
exists only to route a command to a view tool (view_projects / view_prompts / view_prompt_*_log),
which the UI opens in its main window. Tools execute via direct service calls (a `UnitOfWork` on a
short read connection); they are project-agnostic, so the tool context carries no project scope.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.clients.llm.events import Done, TextDelta, ToolCall, ToolCallsReady
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import PromptType
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
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.messages import (
    CONTENT,
    ROLE,
    ROLE_USER,
    assistant_tool_calls_message,
    tool_call_entry,
    tool_reply_message,
    tool_result_payload,
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

    async def dispatch(self, content: str) -> AsyncIterator[dict[str, Any]]:
        prompt = await self._load_prompt()
        chat_messages: list[dict[str, Any]] = [
            {ROLE: ROLE_SYSTEM, CONTENT: prompt.system_prompt},
            {ROLE: ROLE_USER, CONTENT: content},
        ]
        tools = [t.to_openai_tool() for t in catalog_for(PromptType.DISPATCHER)]

        hit_cap = True
        for _turn in range(_MAX_TOOL_TURNS):
            turn_tool_calls: list[ToolCall] = []
            async for event in self._llm.stream_chat(
                model=prompt.model_name,
                messages=chat_messages,
                tools=tools or None,
                temperature=prompt.temperature,
                top_p=prompt.top_p,
                chat_prompt_type=PromptType.DISPATCHER.value,
                chat_prompt_version=prompt.version,
            ):
                if isinstance(event, TextDelta):
                    yield {EVENT: EVENT_TEXT_DELTA, DATA: {DATA_CONTENT: event.content}}
                elif isinstance(event, ToolCallsReady):
                    turn_tool_calls = event.tool_calls
                elif isinstance(event, Done):
                    pass

            if not turn_tool_calls:
                hit_cap = False
                break

            results: list[_ToolResult] = []
            for call in turn_tool_calls:
                args = _parse_args(call.arguments)
                yield {
                    EVENT: EVENT_FUNCTION_CALL,
                    DATA: {DATA_CALL_ID: call.id, DATA_NAME: call.name, DATA_ARGUMENTS: args},
                }
                success, data, errors = await self._execute(call.name, args)
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
            logger.warning("dispatcher tool-turn cap hit")
            yield {
                EVENT: EVENT_UI_NOTICE,
                DATA: {DATA_CONTENT: "Reached tool-call limit; finishing without further actions."},
            }

        yield {EVENT: EVENT_DONE, DATA: {}}

    async def _execute(
        self, name: str, args: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None, list[str] | None]:
        tool = tool_by_name(PromptType.DISPATCHER, name)
        if tool is None:
            return False, None, [f"Unknown tool: {name}"]
        try:
            validated = tool.input_model.model_validate(args)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return False, None, errors
        try:
            async with self._engine.connect() as conn:
                ctx = ToolContext(uow=UnitOfWork(conn), project_uuid=None)
                data = await tool.handler(validated, ctx)
            return True, data, None
        except Exception as exc:
            logger.exception("tool execution failed name=%s", name)
            return False, None, [f"Tool execution failed: {exc}"]

    async def _load_prompt(self) -> PromptVersion:
        async with self._engine.connect() as conn:
            pv = await PromptVersionRepository(conn).get_latest(PromptType.DISPATCHER)
        if pv is None:
            raise PromptVersionNotFoundError("no prompt version for type=dispatcher")
        return pv


def _parse_args(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
