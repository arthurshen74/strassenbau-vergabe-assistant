"""OpenRouter embeddings client.

Sends a batch of strings to the OpenRouter embeddings endpoint and returns one
vector per input. The model slug and the expected vector dimension come from
`settings`; every returned vector is validated against `settings.embedding_dim`
before being handed back to the caller.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from shared.clients.openrouter.usage import LoggingUsageSink, UsageSink, parse_usage
from shared.config import settings
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
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        self._owns_client = client is None
        self._usage_sink = usage_sink or LoggingUsageSink()

    async def embed(
        self,
        texts: list[str],
        *,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

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
