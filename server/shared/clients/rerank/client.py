"""OpenRouter rerank (cross-encoder) client.

Sends a query and a list of candidate documents to the OpenRouter rerank endpoint
and returns the candidates' original indices paired with their relevance scores,
highest first. The model slug comes from `settings.cross_encoder_model`. Reranking
is the only post-retrieval stage in RETRIEVAL.md; it bills `search_units`, recorded
via the usage sink like every other OpenRouter call.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from shared.clients.openrouter.usage import LoggingUsageSink, UsageSink, parse_usage
from shared.config import settings
from shared.models.enums import UsageOperation

logger = logging.getLogger(__name__)

# OpenRouter rerank request fields.
FIELD_MODEL = "model"
FIELD_QUERY = "query"
FIELD_DOCUMENTS = "documents"
FIELD_TOP_N = "top_n"

# OpenRouter rerank response fields.
FIELD_RESULTS = "results"
FIELD_INDEX = "index"
FIELD_RELEVANCE_SCORE = "relevance_score"

HEADER_AUTHORIZATION = "Authorization"
BEARER_PREFIX = "Bearer "

REQUEST_TIMEOUT_SECONDS = 60.0


class RerankClient:
    """Reranks candidate documents against a query via the OpenRouter rerank API."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        self._owns_client = client is None
        self._usage_sink = usage_sink or LoggingUsageSink()

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int,
        project_uuid: UUID | None = None,
    ) -> list[tuple[int, float]]:
        """Return (original_index, relevance_score) pairs, highest score first, length <= top_n."""
        if not documents:
            return []

        payload = {
            FIELD_MODEL: settings.cross_encoder_model,
            FIELD_QUERY: query,
            FIELD_DOCUMENTS: documents,
            FIELD_TOP_N: min(top_n, len(documents)),
        }
        headers = {
            HEADER_AUTHORIZATION: f"{BEARER_PREFIX}{settings.openrouter_api_key}",
        }

        try:
            response = await self._client.post(
                settings.openrouter_api_url_rerank,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Rerank request failed for %d documents", len(documents))
            raise

        body = response.json()
        results = [
            (item[FIELD_INDEX], item[FIELD_RELEVANCE_SCORE]) for item in body[FIELD_RESULTS]
        ]
        results.sort(key=lambda pair: pair[1], reverse=True)

        await self._emit_usage(body, project_uuid)
        return results

    async def _emit_usage(self, body: dict, project_uuid: UUID | None) -> None:
        # Usage recording must never fail the rerank call: swallow and log any error.
        try:
            event = parse_usage(
                body,
                operation=UsageOperation.RERANK,
                model=settings.cross_encoder_model,
                project_uuid=project_uuid,
            )
            if event.cost is None:
                logger.warning("OpenRouter usage missing cost for model %s", event.model)
            await self._usage_sink.emit(event)
        except Exception:
            logger.exception("Failed to record rerank usage; continuing")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
