"""OpenRouter embeddings client.

Sends a batch of strings to the OpenRouter embeddings endpoint and returns one
vector per input. The model slug and the expected vector dimension come from
`settings`; every returned vector is validated against `settings.embedding_dim`
before being handed back to the caller.

An injected `EmbeddingCache` is consulted first: only the texts that miss the
cache are sent to OpenRouter, and the freshly computed vectors are written back.
Usage telemetry is recorded only for the miss batch that actually hit the API.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from shared.clients.embeddings.cache import (
    EmbeddingCache,
    NullEmbeddingCache,
    embedding_cache_key,
)
from shared.clients.openrouter.usage import LoggingUsageSink, UsageSink, parse_usage
from shared.config import settings
from shared.models.embedding_cache import NewEmbeddingCacheEntry
from shared.models.enums import UsageOperation

logger = logging.getLogger(__name__)

# OpenRouter / OpenAI embeddings request fields.
FIELD_MODEL = "model"
FIELD_INPUT = "input"
FIELD_DIMENSIONS = "dimensions"

# OpenRouter / OpenAI embeddings response fields.
FIELD_DATA = "data"
FIELD_EMBEDDING = "embedding"
FIELD_INDEX = "index"

HEADER_AUTHORIZATION = "Authorization"
BEARER_PREFIX = "Bearer "

REQUEST_TIMEOUT_SECONDS = 60.0


class EmbeddingsClient:
    """Embeds batches of text via the OpenRouter embeddings API."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        usage_sink: UsageSink | None = None,
        cache: EmbeddingCache | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        self._owns_client = client is None
        self._usage_sink = usage_sink or LoggingUsageSink()
        self._cache = cache or NullEmbeddingCache()

    async def embed(
        self,
        texts: list[str],
        *,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        keys = [
            embedding_cache_key(settings.embedding_model, settings.embedding_dim, text)
            for text in texts
        ]
        vectors_by_key = await self._cache.get(list(dict.fromkeys(keys)))

        # Unique texts that missed the cache, keyed by cache key, in first-seen order.
        missing: dict[str, str] = {}
        for key, text in zip(keys, texts):
            if key not in vectors_by_key and key not in missing:
                missing[key] = text

        if missing:
            miss_keys = list(missing.keys())
            fresh = await self._embed_remote(
                list(missing.values()), project_uuid, ingest_job_uuid
            )
            for key, vector in zip(miss_keys, fresh):
                vectors_by_key[key] = vector
            await self._cache.put(
                [
                    NewEmbeddingCacheEntry(
                        cache_key=key,
                        model=settings.embedding_model,
                        dim=settings.embedding_dim,
                        embedding=vector,
                    )
                    for key, vector in zip(miss_keys, fresh)
                ]
            )

        return [vectors_by_key[key] for key in keys]

    async def _embed_remote(
        self,
        texts: list[str],
        project_uuid: UUID | None,
        ingest_job_uuid: UUID | None,
    ) -> list[list[float]]:
        payload = {
            FIELD_MODEL: settings.embedding_model,
            FIELD_INPUT: texts,
            FIELD_DIMENSIONS: settings.embedding_dim,
        }
        headers = {
            HEADER_AUTHORIZATION: f"{BEARER_PREFIX}{settings.openrouter_api_key}",
        }

        try:
            response = await self._client.post(
                settings.openrouter_api_url_embedding,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Embeddings request failed for batch of %d", len(texts))
            raise

        body = response.json()
        items = sorted(body[FIELD_DATA], key=lambda item: item[FIELD_INDEX])
        vectors = [item[FIELD_EMBEDDING] for item in items]

        for index, vector in enumerate(vectors):
            if len(vector) != settings.embedding_dim:
                raise ValueError(
                    f"Embedding {index} has dimension {len(vector)}, "
                    f"expected {settings.embedding_dim}"
                )

        await self._emit_usage(body, project_uuid, ingest_job_uuid)
        return vectors

    async def _emit_usage(
        self,
        body: dict,
        project_uuid: UUID | None,
        ingest_job_uuid: UUID | None,
    ) -> None:
        # Usage recording must never fail the embedding call: swallow and log any error.
        try:
            event = parse_usage(
                body,
                operation=UsageOperation.EMBEDDING,
                model=settings.embedding_model,
                project_uuid=project_uuid,
                ingest_job_uuid=ingest_job_uuid,
            )
            if event.cost is None:
                logger.warning("OpenRouter usage missing cost for model %s", event.model)
            await self._usage_sink.emit(event)
        except Exception:
            logger.exception("Failed to record embeddings usage; continuing")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
