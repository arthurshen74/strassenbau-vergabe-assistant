from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from shared.clients.llm.langchain_callback import TelemetryCallbackHandler
from shared.models.enums import PromptType, UsageOperation

_PROVIDER_URL = "https://openrouter.ai/api/v1"
_MODEL = "anthropic/claude-sonnet-4.6"
_LOGGER = "shared.clients.llm.langchain_callback"


def _handler() -> TelemetryCallbackHandler:
    return TelemetryCallbackHandler(
        project_uuid=uuid4(),
        prompt_type=PromptType.PROJECT_CHAT.value,
        provider_url=_PROVIDER_URL,
        chat_model=_MODEL,
    )


def _start(handler: TelemetryCallbackHandler, run_id) -> None:
    handler.on_chat_model_start(
        {},
        [[SystemMessage(content="you are helpful"), HumanMessage(content="hi")]],
        run_id=run_id,
    )


def _llm_result(
    *, with_cost: bool = True, with_usage: bool = True, tool_calls: list | None = None
) -> LLMResult:
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "total_tokens": 140,
        "prompt_tokens_details": {"cached_tokens": 64},
        "completion_tokens_details": {"reasoning_tokens": 12},
    }
    if with_cost:
        usage["cost"] = 0.0021
    message = AIMessage(content="hello there", tool_calls=tool_calls or [])
    generation = ChatGeneration(message=message, generation_info={"finish_reason": "stop"})
    llm_output: dict = {"id": "gen-1", "model_name": _MODEL}
    if with_usage:
        llm_output["token_usage"] = usage
    return LLMResult(generations=[[generation]], llm_output=llm_output)


def test_buffers_usage_and_execution_log() -> None:
    handler = _handler()
    run_id = uuid4()
    _start(handler, run_id)
    tool_calls = [{"name": "retrieve_context", "args": {"query": "x"}, "id": "call-1", "type": "tool_call"}]

    handler.on_llm_end(_llm_result(tool_calls=tool_calls), run_id=run_id)

    usage_events, log_events = handler.drain()

    assert len(usage_events) == 1
    usage = usage_events[0]
    assert usage.operation is UsageOperation.CHAT
    assert usage.model == _MODEL
    assert usage.prompt_tokens == 100 and usage.completion_tokens == 40
    assert usage.cost == Decimal("0.0021")
    assert usage.cached_tokens == 64 and usage.reasoning_tokens == 12
    assert usage.request_id == "gen-1"
    assert usage.chat_prompt_type == PromptType.PROJECT_CHAT.value

    assert len(log_events) == 1
    log = log_events[0]
    assert log.success is True
    assert log.model == _MODEL
    assert log.system_prompt == "you are helpful"
    assert [m["role"] for m in log.messages] == ["system", "user"]
    assert log.response_text == "hello there"
    assert log.response_tool_calls is not None
    assert log.response_tool_calls[0]["name"] == "retrieve_context"
    assert log.response_tool_calls[0]["id"] == "call-1"
    assert log.response_tool_calls[0]["arguments"] == '{"query": "x"}'
    assert log.finish_reason == "stop"
    assert log.tokens_in == 100 and log.tokens_out == 40
    assert log.tools is None and log.response_format is None
    assert log.latency_ms is not None and log.latency_ms >= 0

    # Buffers are cleared after draining.
    assert handler.drain() == ([], [])


def test_missing_cost_buffers_event_and_warns(caplog) -> None:
    handler = _handler()
    run_id = uuid4()
    _start(handler, run_id)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        handler.on_llm_end(_llm_result(with_cost=False), run_id=run_id)

    usage_events, _ = handler.drain()
    assert len(usage_events) == 1 and usage_events[0].cost is None
    assert any("missing cost" in r.getMessage() for r in caplog.records)


def test_missing_token_usage_skips_usage_but_logs_execution(caplog) -> None:
    handler = _handler()
    run_id = uuid4()
    _start(handler, run_id)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        handler.on_llm_end(_llm_result(with_usage=False), run_id=run_id)

    usage_events, log_events = handler.drain()
    assert usage_events == []
    assert len(log_events) == 1
    assert log_events[0].tokens_in is None and log_events[0].tokens_out is None
    assert any("missing token usage" in r.getMessage() for r in caplog.records)


def test_on_llm_error_buffers_failed_execution_log() -> None:
    handler = _handler()
    run_id = uuid4()
    _start(handler, run_id)

    handler.on_llm_error(RuntimeError("boom"), run_id=run_id)

    usage_events, log_events = handler.drain()
    assert usage_events == []
    assert len(log_events) == 1
    log = log_events[0]
    assert log.success is False
    assert log.error_message == "boom"
    assert log.response_text is None
    assert log.messages and log.messages[0]["role"] == "system"
