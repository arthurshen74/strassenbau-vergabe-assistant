from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from shared.clients.llm.client import LLMClient, OutputTruncatedError, RefusalError
from shared.config import settings
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite


def _chat_response(
    content: str = "",
    *,
    finish_reason: str = "stop",
    refusal: str | None = None,
) -> httpx.Response:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if refusal is not None:
        message["refusal"] = refusal
    body = {"choices": [{"finish_reason": finish_reason, "message": message}]}
    return httpx.Response(200, json=body)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> LLMClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(api_key="test-key", client=http)


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


async def test_multi_query_returns_n_strings() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response(json.dumps({"queries": ["q1", "q2", "q3", "q4", "q5"]}))

    client = _client(handler)
    out = await client.multi_query("how to pour concrete", n=3)

    assert isinstance(out, list)
    assert len(out) == 3
    assert all(isinstance(q, str) for q in out)
    assert captured["payload"]["model"] == settings.multi_query_model
    await client.aclose()
