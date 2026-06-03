"""Captures LangChain chat-model telemetry into the same events the LLMClient emits.

LangChain's `ChatOpenAI` (used by the project-chat agent) bypasses `LLMClient`, so its usage and
execution records would otherwise be invisible. `TelemetryCallbackHandler` is a synchronous
`BaseCallbackHandler` that buffers a `UsageEvent` and an `ExecutionLogEvent` per model call. It does
NOT touch the database: the caller drains `usage_events` / `execution_log_events` and emits them to
the DB sinks after the agent run (see `ProjectChatAgent.drain_telemetry`), keeping the writes on the
main event loop the sinks' engine is bound to.

`ChatOpenAI` places OpenRouter's raw `usage` object verbatim at `LLMResult.llm_output["token_usage"]`
(with `cost` when usage accounting is enabled via `extra_body`), so the same `parse_usage` the
clients use builds the `UsageEvent` here too.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import LLMResult

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.openrouter.usage import UsageEvent, parse_usage
from shared.clients.openrouter.usage.parser import FIELD_RESPONSE_ID, FIELD_USAGE
from shared.models.enums import UsageOperation

logger = logging.getLogger(__name__)

# LLMResult.llm_output keys populated by langchain_openai's ChatOpenAI.
LLM_OUTPUT_TOKEN_USAGE = "token_usage"
LLM_OUTPUT_MODEL_NAME = "model_name"

# OpenRouter usage object keys (read from the raw token_usage dict for the execution log).
USAGE_PROMPT_TOKENS = "prompt_tokens"
USAGE_COMPLETION_TOKENS = "completion_tokens"

# LangChain message.type -> OpenAI chat role, so buffered messages match LLMClient-recorded rows.
_ROLE_BY_TYPE = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}
MESSAGE_ROLE = "role"
MESSAGE_CONTENT = "content"

# Mapped tool-call keys, matching the LLMClient ToolCall dump shape.
TOOL_CALL_ID = "id"
TOOL_CALL_NAME = "name"
TOOL_CALL_ARGUMENTS = "arguments"
# langchain_core tool-call dict keys.
LC_TOOL_CALL_NAME = "name"
LC_TOOL_CALL_ARGS = "args"
LC_TOOL_CALL_ID = "id"


@dataclass
class _Pending:
    """The request side of one model call, captured at start and consumed at end."""

    sent_at: datetime
    messages: list[dict[str, Any]]
    system_prompt: str | None


class TelemetryCallbackHandler(BaseCallbackHandler):
    """Buffers a UsageEvent and ExecutionLogEvent per ChatOpenAI call for the caller to drain."""

    def __init__(
        self,
        *,
        project_uuid: UUID,
        prompt_type: str,
        provider_url: str,
        chat_model: str,
    ) -> None:
        self._project_uuid = project_uuid
        self._prompt_type = prompt_type
        self._provider_url = provider_url
        self._chat_model = chat_model
        self._pending: dict[UUID, _Pending] = {}
        self.usage_events: list[UsageEvent] = []
        self.execution_log_events: list[ExecutionLogEvent] = []

    def drain(self) -> tuple[list[UsageEvent], list[ExecutionLogEvent]]:
        """Return the buffered events and clear the buffers."""
        usage, logs = self.usage_events, self.execution_log_events
        self.usage_events = []
        self.execution_log_events = []
        return usage, logs

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        prompt = messages[0] if messages else []
        converted = [self._convert_message(m) for m in prompt]
        system_prompt = next(
            (m.content for m in prompt if m.type == "system" and isinstance(m.content, str)),
            None,
        )
        self._pending[run_id] = _Pending(
            sent_at=datetime.now(UTC), messages=converted, system_prompt=system_prompt
        )

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        returned_at = datetime.now(UTC)
        pending = self._pending.pop(run_id, None)
        llm_output = response.llm_output or {}
        raw_usage = llm_output.get(LLM_OUTPUT_TOKEN_USAGE)
        model = llm_output.get(LLM_OUTPUT_MODEL_NAME) or self._chat_model

        self._buffer_usage(raw_usage, model, llm_output.get(FIELD_RESPONSE_ID))
        self._buffer_execution_log(
            response,
            pending=pending,
            model=model,
            raw_usage=raw_usage,
            request_id=llm_output.get(FIELD_RESPONSE_ID),
            returned_at=returned_at,
            success=True,
            error_message=None,
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        returned_at = datetime.now(UTC)
        pending = self._pending.pop(run_id, None)
        self._buffer_execution_log(
            None,
            pending=pending,
            model=self._chat_model,
            raw_usage=None,
            request_id=None,
            returned_at=returned_at,
            success=False,
            error_message=str(error),
        )

    def _buffer_usage(
        self, raw_usage: Any, model: str, request_id: str | None
    ) -> None:
        # Buffering must never break the agent: swallow and log any error.
        try:
            if not isinstance(raw_usage, dict):
                logger.warning("LangChain chat response missing token usage for model %s", model)
                return
            body = {FIELD_USAGE: raw_usage, FIELD_RESPONSE_ID: request_id}
            event = parse_usage(
                body,
                operation=UsageOperation.CHAT,
                model=model,
                project_uuid=self._project_uuid,
                chat_prompt_type=self._prompt_type,
            )
            if event.cost is None:
                logger.warning("OpenRouter usage missing cost for model %s", event.model)
            self.usage_events.append(event)
        except Exception:
            logger.exception("Failed to buffer LangChain chat usage; continuing")

    def _buffer_execution_log(
        self,
        response: LLMResult | None,
        *,
        pending: _Pending | None,
        model: str,
        raw_usage: Any,
        request_id: str | None,
        returned_at: datetime,
        success: bool,
        error_message: str | None,
    ) -> None:
        # Buffering must never break the agent: swallow and log any error.
        try:
            generation = self._first_generation(response) if response is not None else None
            usage = raw_usage if isinstance(raw_usage, dict) else {}
            sent_at = pending.sent_at if pending is not None else returned_at
            event = ExecutionLogEvent(
                model=model,
                messages=pending.messages if pending is not None else [],
                success=success,
                prompt_type=self._prompt_type,
                provider_url=self._provider_url,
                system_prompt=pending.system_prompt if pending is not None else None,
                response_text=(generation.text or None) if generation is not None else None,
                response_tool_calls=self._tool_calls(generation),
                finish_reason=self._finish_reason(generation),
                tokens_in=usage.get(USAGE_PROMPT_TOKENS),
                tokens_out=usage.get(USAGE_COMPLETION_TOKENS),
                latency_ms=int((returned_at - sent_at).total_seconds() * 1000),
                request_id=request_id,
                project_uuid=self._project_uuid,
                error_message=error_message,
                sent_at=sent_at,
                returned_at=returned_at,
            )
            self.execution_log_events.append(event)
        except Exception:
            logger.exception("Failed to buffer LangChain execution log; continuing")

    @staticmethod
    def _convert_message(message: BaseMessage) -> dict[str, Any]:
        return {
            MESSAGE_ROLE: _ROLE_BY_TYPE.get(message.type, message.type),
            MESSAGE_CONTENT: message.content,
        }

    @staticmethod
    def _first_generation(response: LLMResult) -> Any:
        if response.generations and response.generations[0]:
            return response.generations[0][0]
        return None

    @staticmethod
    def _finish_reason(generation: Any) -> str | None:
        info = getattr(generation, "generation_info", None)
        return info.get("finish_reason") if isinstance(info, dict) else None

    @staticmethod
    def _tool_calls(generation: Any) -> list[dict[str, Any]] | None:
        message = getattr(generation, "message", None)
        if not isinstance(message, AIMessage) or not message.tool_calls:
            return None
        return [
            {
                TOOL_CALL_ID: call.get(LC_TOOL_CALL_ID),
                TOOL_CALL_NAME: call.get(LC_TOOL_CALL_NAME),
                TOOL_CALL_ARGUMENTS: json.dumps(call.get(LC_TOOL_CALL_ARGS, {})),
            }
            for call in message.tool_calls
        ]
