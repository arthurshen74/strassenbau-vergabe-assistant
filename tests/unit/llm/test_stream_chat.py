from __future__ import annotations

import json
from typing import Any

import httpx

from shared.clients.llm.client import LLMClient
from shared.clients.llm.events import Done, TextDelta, ToolCallsReady


def _sse(*chunks: dict[str, Any]) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n" for c in chunks)
    return (body + "data: [DONE]\n").encode()


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event) -> None:
        self.events.append(event)


def _client(content: bytes, *, usage_sink=None, execution_log_sink=None) -> LLMClient:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=content, headers={"content-type": "text/event-stream"}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(
        api_key="k",
        client=http,
        usage_sink=usage_sink,
        execution_log_sink=execution_log_sink,
    )


async def test_stream_text_only() -> None:
    content = _sse(
        {"id": "gen-1", "choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}}]},
        {"choices": [{"finish_reason": "stop"}]},
    )
    client = _client(content)
    events = [
        e
        async for e in client.stream_chat(
            model="x/y", messages=[{"role": "user", "content": "hi"}]
        )
    ]
    await client.aclose()

    assert "".join(e.content for e in events if isinstance(e, TextDelta)) == "Hello"
    assert not any(isinstance(e, ToolCallsReady) for e in events)
    assert isinstance(events[-1], Done) and events[-1].finish_reason == "stop"


async def test_stream_assembles_multi_chunk_tool_calls() -> None:
    content = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "view_projects", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "c2",
                                "function": {"name": "view_lvitem", "arguments": '{"oz":'},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 1, "function": {"arguments": '"01"}'}}]}}]},
        {"choices": [{"finish_reason": "tool_calls"}]},
    )
    client = _client(content)
    events = [
        e
        async for e in client.stream_chat(
            model="x/y",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "view_projects", "parameters": {}}}],
        )
    ]
    await client.aclose()

    ready = [e for e in events if isinstance(e, ToolCallsReady)]
    assert len(ready) == 1
    assert [(c.name, c.arguments) for c in ready[0].tool_calls] == [
        ("view_projects", "{}"),
        ("view_lvitem", '{"oz":"01"}'),
    ]
    assert isinstance(events[-1], Done) and events[-1].finish_reason == "tool_calls"


async def test_stream_emits_usage_and_execution_log() -> None:
    usage_sink = _RecordingSink()
    exec_sink = _RecordingSink()
    content = _sse(
        {"id": "gen-9", "choices": [{"delta": {"content": "hi"}}]},
        {"choices": [{"finish_reason": "stop"}]},
        {"usage": {"prompt_tokens": 3, "completion_tokens": 1, "cost": 0.001}, "choices": []},
    )
    client = _client(content, usage_sink=usage_sink, execution_log_sink=exec_sink)
    _ = [
        e
        async for e in client.stream_chat(
            model="x/y",
            messages=[{"role": "user", "content": "hi"}],
            chat_prompt_type="dispatcher",
            chat_prompt_version=1,
        )
    ]
    await client.aclose()

    assert len(usage_sink.events) == 1
    assert len(exec_sink.events) == 1
    ev = exec_sink.events[0]
    assert ev.model == "x/y"
    assert ev.response_text == "hi"
    assert ev.finish_reason == "stop"
    assert ev.success is True
    assert ev.tokens_in == 3 and ev.tokens_out == 1
    assert ev.prompt_type == "dispatcher" and ev.prompt_version == 1
