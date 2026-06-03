from __future__ import annotations

import httpx
import pytest

from shared.clients.embeddings import EmbeddingsClient, embedding_cache_key
from shared.config import settings
from shared.models.embedding_cache import NewEmbeddingCacheEntry


class _FakeCache:
    """In-memory EmbeddingCache that records how it was called."""

    def __init__(self, seed: dict[str, list[float]] | None = None) -> None:
        self.store: dict[str, list[float]] = dict(seed or {})
        self.get_calls: list[list[str]] = []
        self.put_calls: list[list[NewEmbeddingCacheEntry]] = []

    async def get(self, keys: list[str]) -> dict[str, list[float]]:
        self.get_calls.append(keys)
        return {key: self.store[key] for key in keys if key in self.store}

    async def put(self, entries: list[NewEmbeddingCacheEntry]) -> None:
        self.put_calls.append(entries)
        for entry in entries:
            self.store[entry.cache_key] = entry.embedding


def _vector(value: float) -> list[float]:
    return [value] * settings.embedding_dim


def _response_for(texts: list[str], value_of) -> httpx.Response:
    data = [
        {"index": i, "embedding": value_of(text)} for i, text in enumerate(texts)
    ]
    return httpx.Response(200, json={"data": data})


def test_key_is_deterministic_and_varies() -> None:
    a = embedding_cache_key("model-x", 512, "hello")
    assert a == embedding_cache_key("model-x", 512, "hello")
    assert a != embedding_cache_key("model-y", 512, "hello")
    assert a != embedding_cache_key("model-x", 256, "hello")
    assert a != embedding_cache_key("model-x", 512, "world")


async def test_second_embed_of_same_texts_skips_the_api() -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        texts = json.loads(request.content)["input"]
        calls.append(texts)
        return _response_for(texts, lambda t: _vector(0.5))

    cache = _FakeCache()
    transport = httpx.MockTransport(handler)
    client = EmbeddingsClient(
        client=httpx.AsyncClient(transport=transport), cache=cache
    )

    first = await client.embed(["alpha", "beta"])
    second = await client.embed(["alpha", "beta"])

    assert first == second
    # Only the first call reached the API; the second was served entirely from cache.
    assert calls == [["alpha", "beta"]]


async def test_mixed_hit_miss_sends_only_misses_and_preserves_order() -> None:
    values = {"alpha": 0.1, "beta": 0.2, "gamma": 0.3}
    sent: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        texts = json.loads(request.content)["input"]
        sent.append(texts)
        return _response_for(texts, lambda t: _vector(values[t]))

    # Seed the cache with "beta" only.
    beta_key = embedding_cache_key(
        settings.embedding_model, settings.embedding_dim, "beta"
    )
    cache = _FakeCache({beta_key: _vector(values["beta"])})
    transport = httpx.MockTransport(handler)
    client = EmbeddingsClient(
        client=httpx.AsyncClient(transport=transport), cache=cache
    )

    result = await client.embed(["alpha", "beta", "gamma"])

    # The API saw only the misses, in first-seen order.
    assert sent == [["alpha", "gamma"]]
    # Results are reassembled in input order.
    assert result[0][0] == pytest.approx(0.1)
    assert result[1][0] == pytest.approx(0.2)
    assert result[2][0] == pytest.approx(0.3)
    # The two misses were written back.
    assert len(cache.put_calls) == 1
    assert {e.cache_key for e in cache.put_calls[0]} == {
        embedding_cache_key(settings.embedding_model, settings.embedding_dim, t)
        for t in ("alpha", "gamma")
    }


async def test_all_hits_makes_no_request_and_no_put() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected when every text is cached")

    keys = {
        text: embedding_cache_key(
            settings.embedding_model, settings.embedding_dim, text
        )
        for text in ("alpha", "beta")
    }
    cache = _FakeCache({keys["alpha"]: _vector(0.1), keys["beta"]: _vector(0.2)})
    transport = httpx.MockTransport(handler)
    client = EmbeddingsClient(
        client=httpx.AsyncClient(transport=transport), cache=cache
    )

    result = await client.embed(["alpha", "beta"])

    assert result[0][0] == pytest.approx(0.1)
    assert result[1][0] == pytest.approx(0.2)
    assert cache.put_calls == []
