"""Single OpenRouter transport for every LLM call in the system.

All chat / structured-output traffic goes through `LLMClient`, which targets the OpenRouter
chat-completions endpoint over `httpx`. Callers pass a model slug and, optionally, a Pydantic
output model; with one, the response is JSON-schema-constrained and validated before return.
The two failure modes callers must distinguish are surfaced as `RefusalError` (the model
declined) and `OutputTruncatedError` (the model hit the token limit).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar, overload
from uuid import UUID

import httpx
from pydantic import BaseModel

from shared.clients.llm.events import (
    Done,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallsReady,
)
from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.llm.execution_log_sinks import (
    ExecutionLogSink,
    LoggingExecutionLogSink,
)
from shared.clients.openrouter.usage import LoggingUsageSink, UsageSink, parse_usage
from shared.config import settings
from shared.models.chat_message import ChatMessage
from shared.models.enums import UsageOperation

logger = logging.getLogger(__name__)

# OpenRouter / OpenAI chat-completions request keys.
REQUEST_MODEL = "model"
REQUEST_MESSAGES = "messages"
REQUEST_TEMPERATURE = "temperature"
REQUEST_TOP_P = "top_p"
REQUEST_MAX_TOKENS = "max_tokens"
REQUEST_RESPONSE_FORMAT = "response_format"
REQUEST_TOOLS = "tools"
REQUEST_TOOL_CHOICE = "tool_choice"
REQUEST_STREAM = "stream"
REQUEST_STREAM_OPTIONS = "stream_options"

# response_format / json_schema sub-object keys and the response_format discriminator value.
RESPONSE_FORMAT_TYPE = "type"
RESPONSE_FORMAT_JSON_SCHEMA = "json_schema"
JSON_SCHEMA_NAME = "name"
JSON_SCHEMA_STRICT = "strict"
JSON_SCHEMA_SCHEMA = "schema"

# Provider routing preferences (OpenRouter). require_parameters makes OpenRouter fail the request
# if the routed provider can't honor response_format, rather than silently returning unconstrained
# text; only meaningful when we send a schema.
REQUEST_PROVIDER = "provider"
PROVIDER_REQUIRE_PARAMETERS = "require_parameters"

# Message and response object keys.
MESSAGE_ROLE = "role"
MESSAGE_CONTENT = "content"
MESSAGE_REFUSAL = "refusal"
MESSAGE_TOOL_CALLS = "tool_calls"
ROLE_SYSTEM = "system"

# Response object keys.
RESPONSE_CHOICES = "choices"
RESPONSE_MESSAGE = "message"
RESPONSE_FINISH_REASON = "finish_reason"
RESPONSE_ID = "id"
RESPONSE_USAGE = "usage"
USAGE_PROMPT_TOKENS = "prompt_tokens"
USAGE_COMPLETION_TOKENS = "completion_tokens"

# Streaming SSE wire format + delta / tool-call fragment keys.
STREAM_INCLUDE_USAGE = "include_usage"
SSE_DATA_PREFIX = "data:"
SSE_DONE = "[DONE]"
MESSAGE_DELTA = "delta"
TOOL_CALL_INDEX = "index"
TOOL_CALL_ID = "id"
TOOL_CALL_FUNCTION = "function"
FUNCTION_NAME = "name"
FUNCTION_ARGUMENTS = "arguments"

# finish_reason discriminator values that map to the two caller-visible failure modes.
FINISH_REASON_LENGTH = "length"
FINISH_REASON_CONTENT_FILTER = "content_filter"

DEFAULT_TIMEOUT = 60.0

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for LLM transport failures callers may want to distinguish."""


class RefusalError(LLMError):
    """The model declined to answer (refusal field set, or the response was content-filtered)."""


class OutputTruncatedError(LLMError):
    """The model stopped at the token limit (finish_reason=length); the output is incomplete."""


class LLMClient:
    """OpenRouter chat / structured-output transport built on a shared `httpx.AsyncClient`."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        chat_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        usage_sink: UsageSink | None = None,
        execution_log_sink: ExecutionLogSink | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._chat_url = chat_url or settings.openrouter_api_url_chat
        self._owns_client = client is None
        self._client = client if client is not None else httpx.AsyncClient(timeout=timeout)
        self._usage_sink = usage_sink or LoggingUsageSink()
        self._execution_log_sink = execution_log_sink or LoggingExecutionLogSink()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @overload
    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: None = ...,
        temperature: float | None = ...,
        top_p: float | None = ...,
        max_tokens: int | None = ...,
        chat_prompt_type: str | None = ...,
        chat_prompt_version: int | None = ...,
        project_uuid: UUID | None = ...,
        ingest_job_uuid: UUID | None = ...,
    ) -> str: ...

    @overload
    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: type[T],
        temperature: float | None = ...,
        top_p: float | None = ...,
        max_tokens: int | None = ...,
        chat_prompt_type: str | None = ...,
        chat_prompt_version: int | None = ...,
        project_uuid: UUID | None = ...,
        ingest_job_uuid: UUID | None = ...,
    ) -> T: ...

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: type[T] | None = None,
        temperature: float | None = 0.0,
        top_p: float | None = None,
        max_tokens: int | None = None,
        chat_prompt_type: str | None = None,
        chat_prompt_version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
    ) -> str | T:
        """Run a chat completion. With `output_model`, request JSON-schema-constrained output
        and return a validated instance; without it, return the raw assistant text."""
        payload: dict[str, Any] = {
            REQUEST_MODEL: model,
            REQUEST_MESSAGES: [_serialize_message(m) for m in messages],
        }
        # Omit temperature when None: reasoning models (e.g. gpt-5.x) don't accept the
        # parameter, and with provider.require_parameters set, sending it makes OpenRouter
        # drop every endpoint that can't honor it.
        if temperature is not None:
            payload[REQUEST_TEMPERATURE] = temperature
        if top_p is not None:
            payload[REQUEST_TOP_P] = top_p
        if max_tokens is not None:
            payload[REQUEST_MAX_TOKENS] = max_tokens
        if output_model is not None:
            payload[REQUEST_RESPONSE_FORMAT] = _json_schema_response_format(output_model)
            payload[REQUEST_PROVIDER] = {PROVIDER_REQUIRE_PARAMETERS: True}

        sent_at = datetime.now(UTC)
        response = await self._client.post(self._chat_url, headers=self._headers(), json=payload)
        if response.is_error:
            # Surface the provider's error body (model/routing/schema reason) at the boundary;
            # raise_for_status() otherwise discards it, leaving callers a bare status code.
            logger.error(
                "chat request failed: model=%s status=%s body=%s",
                model,
                response.status_code,
                response.text,
            )
        response.raise_for_status()
        body = response.json()
        returned_at = datetime.now(UTC)

        # Emit usage before the refusal/truncation checks: a content-filtered or length-truncated
        # 200 still bills tokens, so the cost must be recorded even though chat() then raises.
        await self._emit_usage(
            body,
            model=model,
            chat_prompt_type=chat_prompt_type,
            chat_prompt_version=chat_prompt_version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
        )

        choice = body[RESPONSE_CHOICES][0]
        message = choice[RESPONSE_MESSAGE]
        finish_reason = choice.get(RESPONSE_FINISH_REASON)
        refusal = message.get(MESSAGE_REFUSAL)
        content = message.get(MESSAGE_CONTENT) or ""

        is_refusal = bool(refusal) or finish_reason == FINISH_REASON_CONTENT_FILTER
        is_truncated = finish_reason == FINISH_REASON_LENGTH
        error_message = (
            (refusal or "content filtered")
            if is_refusal
            else f"output truncated (finish_reason={finish_reason})"
            if is_truncated
            else None
        )
        success = error_message is None

        # Record the execution log before raising, so a refused/truncated call is still captured.
        await self._emit_execution_log(
            payload,
            body,
            sent_at=sent_at,
            returned_at=returned_at,
            response_text=content,
            response_tool_calls=message.get(MESSAGE_TOOL_CALLS),
            response_structured=_best_effort_json(content) if (output_model and success) else None,
            finish_reason=finish_reason,
            success=success,
            error_message=error_message,
            chat_prompt_type=chat_prompt_type,
            chat_prompt_version=chat_prompt_version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
        )

        if is_refusal:
            logger.warning("LLM refused: model=%s finish_reason=%s", model, finish_reason)
            raise RefusalError(refusal or "content filtered")
        if is_truncated:
            logger.warning("LLM output truncated: model=%s", model)
            raise OutputTruncatedError(error_message or "output truncated")

        if output_model is None:
            return content
        return output_model.model_validate_json(content)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = 0.0,
        top_p: float | None = None,
        max_tokens: int | None = None,
        chat_prompt_type: str | None = None,
        chat_prompt_version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat completion. Yields `TextDelta` as content arrives, then one
        `ToolCallsReady` if the model called tools, then `Done(finish_reason)`. Tools and
        structured output are never combined here. Usage + execution log are emitted once the
        stream ends."""
        payload: dict[str, Any] = {
            REQUEST_MODEL: model,
            REQUEST_MESSAGES: [_serialize_message(m) for m in messages],
            REQUEST_STREAM: True,
            REQUEST_STREAM_OPTIONS: {STREAM_INCLUDE_USAGE: True},
        }
        if temperature is not None:
            payload[REQUEST_TEMPERATURE] = temperature
        if top_p is not None:
            payload[REQUEST_TOP_P] = top_p
        if max_tokens is not None:
            payload[REQUEST_MAX_TOKENS] = max_tokens
        if tools:
            payload[REQUEST_TOOLS] = tools
            if tool_choice is not None:
                payload[REQUEST_TOOL_CHOICE] = tool_choice

        text_parts: list[str] = []
        tool_bufs: dict[int, _ToolCallBuf] = {}
        finish_reason: str | None = None
        usage: dict[str, Any] | None = None
        request_id: str | None = None

        sent_at = datetime.now(UTC)
        async with self._client.stream(
            "POST", self._chat_url, headers=self._headers(), json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith(SSE_DATA_PREFIX):
                    continue
                data_str = line[len(SSE_DATA_PREFIX) :].strip()
                if not data_str:
                    continue
                if data_str == SSE_DONE:
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if data.get(RESPONSE_ID):
                    request_id = data[RESPONSE_ID]
                if data.get(RESPONSE_USAGE):
                    usage = data[RESPONSE_USAGE]
                choices = data.get(RESPONSE_CHOICES) or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get(MESSAGE_DELTA) or {}
                text = delta.get(MESSAGE_CONTENT)
                if text:
                    text_parts.append(text)
                    yield TextDelta(content=text)
                for frag in delta.get(MESSAGE_TOOL_CALLS) or []:
                    idx = frag.get(TOOL_CALL_INDEX, 0)
                    tool_bufs.setdefault(idx, _ToolCallBuf()).merge(frag)
                if choice.get(RESPONSE_FINISH_REASON):
                    finish_reason = choice[RESPONSE_FINISH_REASON]
        returned_at = datetime.now(UTC)

        tool_calls = [
            buf.to_tool_call() for _, buf in sorted(tool_bufs.items()) if buf.is_complete()
        ]
        if tool_calls:
            yield ToolCallsReady(tool_calls=tool_calls)
        yield Done(finish_reason=finish_reason)

        if usage is not None:
            await self._emit_usage(
                {RESPONSE_USAGE: usage, RESPONSE_ID: request_id},
                model=model,
                chat_prompt_type=chat_prompt_type,
                chat_prompt_version=chat_prompt_version,
                project_uuid=project_uuid,
                ingest_job_uuid=ingest_job_uuid,
            )
        is_truncated = finish_reason == FINISH_REASON_LENGTH
        is_refusal = finish_reason == FINISH_REASON_CONTENT_FILTER
        error_message = (
            f"output truncated (finish_reason={finish_reason})"
            if is_truncated
            else "content filtered"
            if is_refusal
            else None
        )
        await self._emit_execution_log(
            payload,
            {RESPONSE_USAGE: usage or {}, RESPONSE_ID: request_id},
            sent_at=sent_at,
            returned_at=returned_at,
            response_text="".join(text_parts) or None,
            response_tool_calls=[tc.model_dump() for tc in tool_calls] or None,
            response_structured=None,
            finish_reason=finish_reason,
            success=error_message is None,
            error_message=error_message,
            chat_prompt_type=chat_prompt_type,
            chat_prompt_version=chat_prompt_version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
        )

    async def _emit_usage(
        self,
        body: dict[str, Any],
        *,
        model: str,
        chat_prompt_type: str | None,
        chat_prompt_version: int | None,
        project_uuid: UUID | None,
        ingest_job_uuid: UUID | None,
    ) -> None:
        # Usage recording must never fail the chat call: swallow and log any error.
        try:
            event = parse_usage(
                body,
                operation=UsageOperation.CHAT,
                model=model,
                project_uuid=project_uuid,
                ingest_job_uuid=ingest_job_uuid,
                chat_prompt_type=chat_prompt_type,
                chat_prompt_version=chat_prompt_version,
            )
            if event.cost is None:
                logger.warning("OpenRouter usage missing cost for model %s", event.model)
            await self._usage_sink.emit(event)
        except Exception:
            logger.exception("Failed to record chat usage; continuing")

    async def _emit_execution_log(
        self,
        payload: dict[str, Any],
        body: dict[str, Any],
        *,
        sent_at: datetime,
        returned_at: datetime,
        response_text: str | None,
        response_tool_calls: list[dict[str, Any]] | None,
        response_structured: dict[str, Any] | None,
        finish_reason: str | None,
        success: bool,
        error_message: str | None,
        chat_prompt_type: str | None,
        chat_prompt_version: int | None,
        project_uuid: UUID | None,
        ingest_job_uuid: UUID | None,
    ) -> None:
        # Execution logging must never fail the chat call: swallow and log any error.
        try:
            messages: list[dict[str, Any]] = payload.get(REQUEST_MESSAGES, [])
            system_prompt = next(
                (m.get(MESSAGE_CONTENT) for m in messages if m.get(MESSAGE_ROLE) == ROLE_SYSTEM),
                None,
            )
            usage = body.get(RESPONSE_USAGE) or {}
            event = ExecutionLogEvent(
                model=payload[REQUEST_MODEL],
                messages=messages,
                success=success,
                prompt_type=chat_prompt_type,
                prompt_version=chat_prompt_version,
                provider_url=self._chat_url,
                system_prompt=system_prompt,
                tools=payload.get(REQUEST_TOOLS),
                response_format=payload.get(REQUEST_RESPONSE_FORMAT),
                response_text=response_text,
                response_tool_calls=response_tool_calls,
                response_structured=response_structured,
                finish_reason=finish_reason,
                tokens_in=usage.get(USAGE_PROMPT_TOKENS),
                tokens_out=usage.get(USAGE_COMPLETION_TOKENS),
                latency_ms=int((returned_at - sent_at).total_seconds() * 1000),
                request_id=body.get(RESPONSE_ID),
                project_uuid=project_uuid,
                ingest_job_uuid=ingest_job_uuid,
                error_message=error_message,
                sent_at=sent_at,
                returned_at=returned_at,
            )
            await self._execution_log_sink.emit(event)
        except Exception:
            logger.exception("Failed to record execution log; continuing")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


def _serialize_message(message: ChatMessage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(message, BaseModel):
        return message.model_dump()
    return dict(message)


def _best_effort_json(text: str) -> dict[str, Any] | None:
    """Parse `text` as a JSON object for logging; return None if it isn't one."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class _ToolCallBuf:
    """Assembles one streamed tool call: id/name arrive first, arguments append across chunks."""

    def __init__(self) -> None:
        self.id: str | None = None
        self.name: str | None = None
        self.arguments = ""

    def merge(self, frag: Mapping[str, Any]) -> None:
        if frag.get(TOOL_CALL_ID):
            self.id = frag[TOOL_CALL_ID]
        fn = frag.get(TOOL_CALL_FUNCTION) or {}
        if fn.get(FUNCTION_NAME):
            self.name = fn[FUNCTION_NAME]
        if fn.get(FUNCTION_ARGUMENTS):
            self.arguments += fn[FUNCTION_ARGUMENTS]

    def is_complete(self) -> bool:
        return bool(self.id and self.name)

    def to_tool_call(self) -> ToolCall:
        assert self.id is not None and self.name is not None
        return ToolCall(id=self.id, name=self.name, arguments=self.arguments or "{}")


def _json_schema_response_format(output_model: type[BaseModel]) -> dict[str, Any]:
    return {
        RESPONSE_FORMAT_TYPE: RESPONSE_FORMAT_JSON_SCHEMA,
        RESPONSE_FORMAT_JSON_SCHEMA: {
            JSON_SCHEMA_NAME: output_model.__name__,
            JSON_SCHEMA_STRICT: True,
            JSON_SCHEMA_SCHEMA: output_model.model_json_schema(),
        },
    }
