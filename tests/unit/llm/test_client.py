from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from shared.clients.llm.client import LLMClient, OutputTruncatedError, RefusalError
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite


def _chat_response(
    content: str = "",
    *,
    finish_reason: str = "stop",
    refusal: str | None = None,
    usage: dict[str, Any] | None = None,
    response_id: str | None = None,
) -> httpx.Response:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if refusal is not None:
        message["refusal"] = refusal
    body: dict[str, Any] = {"choices": [{"finish_reason": finish_reason, "message": message}]}
    if usage is not None:
        body["usage"] = usage
    if response_id is not None:
        body["id"] = response_id
    return httpx.Response(200, json=body)


def _client(handler: Callable[[httpx.Request], httpx.Response], usage_sink=None) -> LLMClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(api_key="test-key", client=http, usage_sink=usage_sink)


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event) -> None:
        self.events.append(event)


class _RaisingSink:
    async def emit(self, event) -> None:
        raise RuntimeError("sink is down")


_CHAT_USAGE = {
    "prompt_tokens": 100,
    "completion_tokens": 40,
    "total_tokens": 140,
    "cost": 0.0021,
    "prompt_tokens_details": {"cached_tokens": 64},
    "completion_tokens_details": {"reasoning_tokens": 12},
}


async def test_chat_returns_raw_text_without_output_model() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return _chat_response("hello there")

    client = _client(handler)
    out = await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])

    assert out == "hello there"
    assert captured["auth"] == "Bearer test-key"
    assert "response_format" not in captured["payload"]
    assert "provider" not in captured["payload"]
    await client.aclose()


async def test_chat_omits_temperature_when_none() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response("ok")

    client = _client(handler)
    await client.chat(
        model="x/y", messages=[{"role": "user", "content": "hi"}], temperature=None
    )

    assert "temperature" not in captured["payload"]
    await client.aclose()


async def test_chat_sends_temperature_when_set() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response("ok")

    client = _client(handler)
    await client.chat(
        model="x/y", messages=[{"role": "user", "content": "hi"}], temperature=0.0
    )

    assert captured["payload"]["temperature"] == 0.0
    await client.aclose()


async def test_chat_structured_output_returns_validated_model() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response(json.dumps({"queries": ["a", "b"]}))

    client = _client(handler)
    out = await client.chat(
        model="x/y",
        messages=[{"role": "user", "content": "hi"}],
        output_model=MultiQueryRewrite,
    )

    assert isinstance(out, MultiQueryRewrite)
    assert out.queries == ["a", "b"]
    response_format = captured["payload"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "MultiQueryRewrite"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert captured["payload"]["provider"] == {"require_parameters": True}
    await client.aclose()


async def test_chat_refusal_field_raises_refusal_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("", refusal="I can't help with that.")

    client = _client(handler)
    with pytest.raises(RefusalError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    await client.aclose()


async def test_chat_content_filter_finish_raises_refusal_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("", finish_reason="content_filter")

    client = _client(handler)
    with pytest.raises(RefusalError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    await client.aclose()


async def test_chat_length_finish_raises_output_truncated_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("partial", finish_reason="length")

    client = _client(handler)
    with pytest.raises(OutputTruncatedError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    await client.aclose()


async def test_chat_emits_usage_event() -> None:
    from decimal import Decimal
    from uuid import uuid4

    from shared.models.enums import UsageOperation

    sink = _RecordingSink()
    project_uuid = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("hi", usage=_CHAT_USAGE, response_id="gen-xyz")

    client = _client(handler, usage_sink=sink)
    await client.chat(
        model="x/y",
        messages=[{"role": "user", "content": "hi"}],
        chat_prompt_type="project_chat",
        chat_prompt_version=3,
        project_uuid=project_uuid,
    )

    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.operation is UsageOperation.CHAT
    assert event.model == "x/y"
    assert event.prompt_tokens == 100
    assert event.completion_tokens == 40
    assert event.cost == Decimal("0.0021")
    assert event.cached_tokens == 64
    assert event.reasoning_tokens == 12
    assert event.request_id == "gen-xyz"
    assert event.chat_prompt_type == "project_chat"
    assert event.chat_prompt_version == 3
    assert event.project_uuid == project_uuid
    await client.aclose()


async def test_chat_refusal_still_emits_usage_before_raising() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("", refusal="no", usage=_CHAT_USAGE)

    client = _client(handler, usage_sink=sink)
    with pytest.raises(RefusalError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])

    assert len(sink.events) == 1
    assert sink.events[0].total_tokens == 140
    await client.aclose()


async def test_chat_truncated_still_emits_usage_before_raising() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("partial", finish_reason="length", usage=_CHAT_USAGE)

    client = _client(handler, usage_sink=sink)
    with pytest.raises(OutputTruncatedError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])

    assert len(sink.events) == 1
    await client.aclose()


async def test_chat_sink_failure_is_isolated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("hello", usage=_CHAT_USAGE)

    client = _client(handler, usage_sink=_RaisingSink())
    out = await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])

    assert out == "hello"
    await client.aclose()


async def test_chat_no_usage_emit_on_http_error() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client(handler, usage_sink=sink)
    with pytest.raises(httpx.HTTPStatusError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    assert sink.events == []
    await client.aclose()
