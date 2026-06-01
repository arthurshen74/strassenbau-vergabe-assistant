"""OpenRouter embeddings client.

Sends a batch of strings to the OpenRouter embeddings endpoint and returns one
vector per input. The model slug and the expected vector dimension come from
`settings`; every returned vector is validated against `settings.embedding_dim`
before being handed back to the caller.
"""

from __future__ import annotations

import logging

import httpx

from shared.config import settings

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

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        self._owns_client = client is None

    async def embed(self, texts: list[str]) -> list[list[float]]:
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

        items = sorted(response.json()[FIELD_DATA], key=lambda item: item[FIELD_INDEX])
        vectors = [item[FIELD_EMBEDDING] for item in items]

        for index, vector in enumerate(vectors):
            if len(vector) != settings.embedding_dim:
                raise ValueError(
                    f"Embedding {index} has dimension {len(vector)}, "
                    f"expected {settings.embedding_dim}"
                )

        return vectors

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
