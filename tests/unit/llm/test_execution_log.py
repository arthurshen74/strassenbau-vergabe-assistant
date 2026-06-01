from __future__ import annotations

from typing import Any

import httpx
import pytest

from shared.clients.llm.client import LLMClient, RefusalError


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event) -> None:
        self.events.append(event)


def _client(body: dict[str, Any], exec_sink) -> LLMClient:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(api_key="k", client=http, execution_log_sink=exec_sink)


async def test_chat_emits_execution_log() -> None:
    sink = _RecordingSink()
    body = {
        "id": "gen-1",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    client = _client(body, sink)
    out = await client.chat(
        model="x/y",
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ],
        chat_prompt_type="project_chat",
        chat_prompt_version=2,
    )
    await client.aclose()

    assert out == "hello"
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.success is True
    assert ev.response_text == "hello"
    assert ev.finish_reason == "stop"
    assert ev.system_prompt == "sys"
    assert ev.tokens_in == 5 and ev.tokens_out == 2
    assert ev.prompt_type == "project_chat" and ev.prompt_version == 2
    assert ev.request_id == "gen-1"


async def test_chat_refusal_still_logs_with_success_false() -> None:
    sink = _RecordingSink()
    body = {
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": "", "refusal": "no"}}
        ]
    }
    client = _client(body, sink)
    with pytest.raises(RefusalError):
        await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    await client.aclose()

    assert len(sink.events) == 1
    assert sink.events[0].success is False
    assert sink.events[0].error_message == "no"


async def test_execution_log_sink_failure_is_isolated() -> None:
    class _Raising:
        async def emit(self, event) -> None:
            raise RuntimeError("sink down")

    body = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    client = LLMClient(api_key="k", client=http, execution_log_sink=_Raising())
    out = await client.chat(model="x/y", messages=[{"role": "user", "content": "hi"}])
    await client.aclose()
    assert out == "ok"
