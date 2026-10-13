from __future__ import annotations

import json
import os

import httpx
import pytest

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.embeddings.client import (
    FIELD_DIMENSIONS,
    FIELD_INPUT,
    FIELD_MODEL,
    HEADER_AUTHORIZATION,
)
from shared.config import settings


def _embeddings_response(vectors: list[list[float]]) -> httpx.Response:
    data = [
        {"object": "embedding", "index": index, "embedding": vector}
        for index, vector in enumerate(vectors)
    ]
    return httpx.Response(200, json={"object": "list", "data": data})


def _client_with_handler(handler, usage_sink=None) -> EmbeddingsClient:
    transport = httpx.MockTransport(handler)
    return EmbeddingsClient(
        client=httpx.AsyncClient(transport=transport), usage_sink=usage_sink
    )


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event) -> None:
        self.events.append(event)


class _RaisingSink:
    async def emit(self, event) -> None:
        raise RuntimeError("sink is down")


def _response_with_usage(vectors, usage) -> httpx.Response:
    data = [
        {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
    ]
    body: dict = {"object": "list", "id": "emb-1", "data": data}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


async def test_embed_returns_vectors_and_sends_expected_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get(HEADER_AUTHORIZATION)
        captured["body"] = json.loads(request.content)
        vectors = [[0.1] * settings.embedding_dim, [0.2] * settings.embedding_dim]
        return _embeddings_response(vectors)

    client = _client_with_handler(handler)
    result = await client.embed(["alpha", "beta"])

    assert len(result) == 2
    assert all(len(vector) == settings.embedding_dim for vector in result)
    assert result[0][0] == 0.1
    assert result[1][0] == 0.2

    assert captured["url"] == settings.openrouter_api_url_embedding
    assert captured["auth"] == f"Bearer {settings.openrouter_api_key}"
    body = captured["body"]
    assert body[FIELD_MODEL] == settings.embedding_model
    assert body[FIELD_INPUT] == ["alpha", "beta"]
    assert body[FIELD_DIMENSIONS] == settings.embedding_dim


async def test_embed_orders_vectors_by_response_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = [
            {"index": 1, "embedding": [0.2] * settings.embedding_dim},
            {"index": 0, "embedding": [0.1] * settings.embedding_dim},
        ]
        return httpx.Response(200, json={"data": data})

    client = _client_with_handler(handler)
    result = await client.embed(["first", "second"])

    assert result[0][0] == 0.1
    assert result[1][0] == 0.2


async def test_embed_raises_on_wrong_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        short_vector = [0.1] * (settings.embedding_dim - 1)
        return _embeddings_response([short_vector])

    client = _client_with_handler(handler)
    with pytest.raises(ValueError, match="dimension"):
        await client.embed(["alpha"])


async def test_embed_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with_handler(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.embed(["alpha"])


async def test_embed_empty_batch_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected for an empty batch")

    client = _client_with_handler(handler)
    assert await client.embed([]) == []


async def test_embed_splits_misses_into_batches(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)[FIELD_INPUT]
        requests.append(texts)
        return _embeddings_response(
            [[float(len(text))] * settings.embedding_dim for text in texts]
        )

    client = _client_with_handler(handler)
    result = await client.embed(["a", "bb", "ccc", "dddd", "eeeee"])

    assert requests == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert [vector[0] for vector in result] == [1.0, 2.0, 3.0, 4.0, 5.0]


async def test_embed_emits_usage_event_to_sink() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        vectors = [[0.1] * settings.embedding_dim]
        usage = {"prompt_tokens": 8, "total_tokens": 8, "cost": 0.0000004}
        return _response_with_usage(vectors, usage)

    client = _client_with_handler(handler, usage_sink=sink)
    await client.embed(["alpha"])

    assert len(sink.events) == 1
    from decimal import Decimal

    from shared.models.enums import UsageOperation

    event = sink.events[0]
    assert event.operation is UsageOperation.EMBEDDING
    assert event.model == settings.embedding_model
    assert event.prompt_tokens == 8
    assert event.total_tokens == 8
    assert event.cost == Decimal("0.0000004")
    assert event.request_id == "emb-1"


async def test_embed_forwards_attribution_to_usage_event() -> None:
    from uuid import uuid4

    sink = _RecordingSink()
    project_uuid, job_uuid, document_uuid = uuid4(), uuid4(), uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        vectors = [[0.1] * settings.embedding_dim]
        return _response_with_usage(vectors, {"prompt_tokens": 8, "total_tokens": 8, "cost": 0.1})

    client = _client_with_handler(handler, usage_sink=sink)
    await client.embed(
        ["alpha"],
        project_uuid=project_uuid,
        ingest_job_uuid=job_uuid,
        document_uuid=document_uuid,
    )

    # Ingestion embeddings must carry the owning document so the usage row attributes to it.
    event = sink.events[0]
    assert event.project_uuid == project_uuid
    assert event.ingest_job_uuid == job_uuid
    assert event.document_uuid == document_uuid


async def test_embed_missing_cost_records_none_and_warns(caplog) -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        vectors = [[0.1] * settings.embedding_dim]
        return _response_with_usage(vectors, {"prompt_tokens": 8, "total_tokens": 8})

    client = _client_with_handler(handler, usage_sink=sink)
    with caplog.at_level("WARNING", logger="shared.clients.embeddings.client"):
        await client.embed(["alpha"])

    assert sink.events[0].cost is None
    assert any("missing cost" in r.getMessage() for r in caplog.records)


async def test_embed_missing_usage_does_not_emit_or_crash() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return _response_with_usage([[0.1] * settings.embedding_dim], usage=None)

    client = _client_with_handler(handler, usage_sink=sink)
    result = await client.embed(["alpha"])

    assert len(result) == 1
    assert sink.events == []


async def test_embed_sink_failure_is_isolated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        vectors = [[0.1] * settings.embedding_dim]
        return _response_with_usage(vectors, {"prompt_tokens": 8, "total_tokens": 8, "cost": 0.1})

    client = _client_with_handler(handler, usage_sink=_RaisingSink())
    result = await client.embed(["alpha"])

    assert len(result) == 1


async def test_embed_no_usage_emit_on_http_error() -> None:
    sink = _RecordingSink()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with_handler(handler, usage_sink=sink)
    with pytest.raises(httpx.HTTPStatusError):
        await client.embed(["alpha"])
    assert sink.events == []


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_TEST"),
    reason="set OPENROUTER_LIVE_TEST=1 (with OPENROUTER_API_KEY) to run the live call",
)
async def test_embed_live() -> None:
    sink = _RecordingSink()
    client = EmbeddingsClient(usage_sink=sink)
    try:
        result = await client.embed(["hello world", "second input"])
    finally:
        await client.aclose()

    assert len(result) == 2
    assert all(len(vector) == settings.embedding_dim for vector in result)

    # Confirms the OpenAPI spec empirically: embeddings responses carry usage.cost + total_tokens.
    assert len(sink.events) == 1
    assert sink.events[0].cost is not None
    assert sink.events[0].total_tokens is not None
