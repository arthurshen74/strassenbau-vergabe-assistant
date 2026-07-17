"""An execution-log sink that emits each LLM call as an OpenInference span for Phoenix.

The custom httpx `LLMClient` is invisible to the LangChain auto-instrumentor (it is
neither a LangChain model nor the openai SDK), so dispatch and the calculator's in-node
model calls would otherwise produce no LLM spans. This sink converts the
`ExecutionLogEvent` the client already emits into an OpenInference `LLM` span -- model,
input/output messages, token counts -- carrying the original wall-clock timing
(`sent_at`/`returned_at`). Created with the ambient context as parent, so when the call
ran inside a `flow_span` root (dispatch, calculator) the span nests into that trace;
otherwise it stands alone. It is teed alongside the DB sink (see factory), never used
for project chat -- that path is traced by the LangChain instrumentor instead.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openinference.semconv.trace import (
    MessageAttributes,
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
    ToolAttributes,
)
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from shared.clients.llm.execution_log import ExecutionLogEvent

_tracer = trace.get_tracer(__name__)

# Span-name suffix when a call carries no prompt_type (e.g. the aggregate-LV helper).
_DEFAULT_OP = "chat"
# Assistant is the only role the model speaks in.
_ROLE_ASSISTANT = "assistant"

_NS_PER_SECOND = 1_000_000_000


class OTelExecutionLogSink:
    """Emits one OpenInference LLM span per execution-log event; see module
    docstring."""

    async def emit(self, event: ExecutionLogEvent) -> None:
        span = _tracer.start_span(
            f"llm.{event.prompt_type or _DEFAULT_OP}",
            start_time=_epoch_ns(event.sent_at),
        )
        try:
            span.set_attributes(_llm_span_attributes(event))
            if event.success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(
                    Status(StatusCode.ERROR, event.error_message or "llm call failed")
                )
        finally:
            span.end(end_time=_epoch_ns(event.returned_at))


def _llm_span_attributes(event: ExecutionLogEvent) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
        SpanAttributes.LLM_MODEL_NAME: event.model,
        SpanAttributes.INPUT_VALUE: _json(event.messages),
        SpanAttributes.INPUT_MIME_TYPE: OpenInferenceMimeTypeValues.JSON.value,
    }
    for i, message in enumerate(event.messages):
        role = message.get("role")
        content = message.get("content")
        prefix = f"{SpanAttributes.LLM_INPUT_MESSAGES}.{i}.{{}}"
        if role is not None:
            attrs[prefix.format(MessageAttributes.MESSAGE_ROLE)] = str(role)
        if content is not None:
            attrs[prefix.format(MessageAttributes.MESSAGE_CONTENT)] = _as_text(content)

    output_value, output_is_json = _output(event)
    if output_value is not None:
        attrs[SpanAttributes.OUTPUT_VALUE] = output_value
        attrs[SpanAttributes.OUTPUT_MIME_TYPE] = (
            OpenInferenceMimeTypeValues.JSON
            if output_is_json
            else OpenInferenceMimeTypeValues.TEXT
        ).value
        out = f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.0.{{}}"
        attrs[out.format(MessageAttributes.MESSAGE_ROLE)] = _ROLE_ASSISTANT
        attrs[out.format(MessageAttributes.MESSAGE_CONTENT)] = output_value

    if event.tokens_in is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] = event.tokens_in
    if event.tokens_out is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = event.tokens_out
    if event.tokens_in is not None and event.tokens_out is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] = event.tokens_in + event.tokens_out

    for i, tool in enumerate(event.tools or []):
        attrs[f"{SpanAttributes.LLM_TOOLS}.{i}.{ToolAttributes.TOOL_JSON_SCHEMA}"] = (
            _json(tool)
        )
    if event.response_format is not None:
        attrs[SpanAttributes.LLM_INVOCATION_PARAMETERS] = _json(
            {"response_format": event.response_format}
        )

    if event.conversation_uuid is not None:
        attrs[SpanAttributes.SESSION_ID] = str(event.conversation_uuid)
    attrs[SpanAttributes.METADATA] = _json(
        {
            "prompt_type": event.prompt_type,
            "prompt_version": event.prompt_version,
            "request_id": event.request_id,
            "provider_url": event.provider_url,
            "finish_reason": event.finish_reason,
            "latency_ms": event.latency_ms,
            "project_uuid": str(event.project_uuid) if event.project_uuid else None,
            "conversation_uuid": str(event.conversation_uuid)
            if event.conversation_uuid
            else None,
            "ingest_job_uuid": str(event.ingest_job_uuid)
            if event.ingest_job_uuid
            else None,
        }
    )
    return attrs


def _output(event: ExecutionLogEvent) -> tuple[str | None, bool]:
    """The single output value and whether it is JSON: plain text, else structured
    output, else the assistant's tool calls."""
    if event.response_text is not None:
        return event.response_text, False
    if event.response_structured is not None:
        return _json(event.response_structured), True
    if event.response_tool_calls is not None:
        return _json(event.response_tool_calls), True
    return None, False


def _as_text(content: Any) -> str:
    return content if isinstance(content, str) else _json(content)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _epoch_ns(when: datetime | None) -> int | None:
    return int(when.timestamp() * _NS_PER_SECOND) if when is not None else None
