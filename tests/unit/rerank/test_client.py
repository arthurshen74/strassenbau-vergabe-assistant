from __future__ import annotations

import json
import os

import httpx
import pytest

from shared.clients.rerank import RerankClient
from shared.clients.rerank.client import (
    FIELD_DOCUMENTS,
    FIELD_MODEL,
    FIELD_QUERY,
    FIELD_TOP_N,
    HEADER_AUTHORIZATION,
)
from shared.config import settings
from shared.models.enums import UsageOperation


def _rerank_response(results, usage=None) -> httpx.Response:
    body: dict = {"id": "rr-1", "results": results}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def _client_with_handler(handler, usage_sink=None) -> RerankClient:
    transport = httpx.MockTransport(handler)
    return RerankClient(client=httpx.AsyncClient(transport=transport), usage_sink=usage_sink)


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event) -> None:
        self.events.append(event)


class _RaisingSink:
    async def emit(self, event) -> None:
        raise RuntimeError("sink is down")


async def test_rerank_sends_expected_request_and_sorts_results() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get(HEADER_AUTHORIZATION)
        captured["body"] = json.loads(request.content)
        results = [
            {"index": 0, "relevance_score": 0.2},
            {"index": 2, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.5},
        ]
        return _rerank_response(results)

    client = _client_with_handler(handler)
    ranked = await client.rerank("q", ["a", "b", "c"], top_n=3)

    assert ranked == [(2, 0.9), (1, 0.5), (0, 0.2)]
    assert captured["url"] == settings.openrouter_api_url_rerank
    assert captured["auth"] == f"Bearer {settings.openrouter_api_key}"
    body = captured["body"]
    assert body[FIELD_MODEL] == settings.cross_encoder_model
    assert body[FIELD_QUERY] == "q"
    assert body[FIELD_DOCUMENTS] == ["a", "b", "c"]
    assert body[FIELD_TOP_N] == 3


async def test_rerank_clamps_top_n_to_document_count() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _rerank_response([{"index": 0, "relevance_score": 0.4}])

    client = _client_with_handler(handler)
    await client.rerank("q", ["only"], top_n=10)

    assert captured["body"][FIELD_TOP_N] == 1


async def test_rerank_empty_documents_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected for empty documents")

    client = _client_with_handler(handler)
    assert await client.rerank("q", [], top_n=5) == []


async def test_rerank_raises_on_http_error_and_emits_no_usage() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with_handler(handler, usage_sink=sink)
    with pytest.raises(httpx.HTTPStatusError):
        await client.rerank("q", ["a"], top_n=1)
    assert sink.events == []


async def test_rerank_emits_usage_with_search_units() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        usage = {"search_units": 1, "cost": 0.002}
        return _rerank_response([{"index": 0, "relevance_score": 0.4}], usage=usage)

    client = _client_with_handler(handler, usage_sink=sink)
    await client.rerank("q", ["a"], top_n=1)

    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.operation is UsageOperation.RERANK
    assert event.model == settings.cross_encoder_model
    assert event.search_units == 1


async def test_rerank_missing_usage_does_not_emit_or_crash() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return _rerank_response([{"index": 0, "relevance_score": 0.4}], usage=None)

    client = _client_with_handler(handler, usage_sink=sink)
    ranked = await client.rerank("q", ["a"], top_n=1)

    assert ranked == [(0, 0.4)]
    assert sink.events == []


async def test_rerank_sink_failure_is_isolated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        usage = {"search_units": 1, "cost": 0.002}
        return _rerank_response([{"index": 0, "relevance_score": 0.4}], usage=usage)

    client = _client_with_handler(handler, usage_sink=_RaisingSink())
    ranked = await client.rerank("q", ["a"], top_n=1)

    assert ranked == [(0, 0.4)]


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_TEST"),
    reason="set OPENROUTER_LIVE_TEST=1 (with OPENROUTER_API_KEY) to run the live call",
)
async def test_rerank_live() -> None:
    sink = _RecordingSink()
    client = RerankClient(usage_sink=sink)
    try:
        ranked = await client.rerank(
            "asphalt base layer requirements",
            ["Requirements for the asphalt base layer.", "Unrelated text about migratory birds."],
            top_n=2,
        )
    finally:
        await client.aclose()

    assert len(ranked) == 2
    # the relevant document (index 0) should rank first
    assert ranked[0][0] == 0
    # confirms the rerank response carries usage with search_units
    assert len(sink.events) == 1
    assert sink.events[0].search_units is not None
