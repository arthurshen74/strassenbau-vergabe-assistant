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


def _client_with_handler(handler) -> EmbeddingsClient:
    transport = httpx.MockTransport(handler)
    return EmbeddingsClient(client=httpx.AsyncClient(transport=transport))


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


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_TEST"),
    reason="set OPENROUTER_LIVE_TEST=1 (with OPENROUTER_API_KEY) to run the live call",
)
async def test_embed_live() -> None:
    client = EmbeddingsClient()
    try:
        result = await client.embed(["hello world", "second input"])
    finally:
        await client.aclose()

    assert len(result) == 2
    assert all(len(vector) == settings.embedding_dim for vector in result)
