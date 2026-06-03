"""Embedding cache injected into the ``EmbeddingsClient``.

The client consults a cache before calling OpenRouter and only embeds the misses. The cache key
is a SHA-256 hex of the embedding model, the vector dimension, and the exact input text, so a
change to either the model or the dimension is a clean miss rather than a stale hit.

``NullEmbeddingCache`` is the default no-op (used in tests and when caching is disabled).
``PostgresEmbeddingCache`` owns an ``AsyncEngine`` and opens its own short transaction per call,
the same pattern as ``DatabaseUsageSink`` -- cache reads/writes are independent of any caller
``UnitOfWork``.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.embedding_cache import NewEmbeddingCacheEntry
from shared.repositories.embedding_cache import EmbeddingCacheRepository

# Components of the cache key, joined before hashing. The separator cannot appear in a model slug
# or an integer, so distinct (model, dim, text) triples never collide on the same key.
KEY_SEPARATOR = "\x00"


def embedding_cache_key(model: str, dim: int, text: str) -> str:
    raw = KEY_SEPARATOR.join((model, str(dim), text))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@runtime_checkable
class EmbeddingCache(Protocol):
    async def get(self, keys: list[str]) -> dict[str, list[float]]: ...

    async def put(self, entries: list[NewEmbeddingCacheEntry]) -> None: ...


class NullEmbeddingCache:
    """No-op cache: every lookup misses and writes are dropped."""

    async def get(self, keys: list[str]) -> dict[str, list[float]]:
        return {}

    async def put(self, entries: list[NewEmbeddingCacheEntry]) -> None:
        return None


class PostgresEmbeddingCache:
    """Reads/writes cached embeddings in Postgres, each call in its own transaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        async with self._engine.connect() as conn:
            return await EmbeddingCacheRepository(conn).get_many(keys)

    async def put(self, entries: list[NewEmbeddingCacheEntry]) -> None:
        if not entries:
            return
        async with self._engine.begin() as conn:
            await EmbeddingCacheRepository(conn).put_many(entries)
