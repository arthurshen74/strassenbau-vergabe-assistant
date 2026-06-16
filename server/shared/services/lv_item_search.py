"""Hybrid search over a project's LV item positions.

Runs the same dense kNN + BM25 lexical retrieval the RAG pipeline uses, scoped to the project's
LV_ITEM chunks (lv_items_filter) and resolved back to the LVItem rows the LVItems table renders.
An exact oz/stl_nr position-number match is surfaced ahead of the fused text results, so typing a
position number jumps straight to that item. One LV item owns many chunks, so the ranked chunks
are collapsed to their distinct LV item before the rows are loaded and re-ordered by relevance.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.search import SearchClient, lv_items_filter
from shared.clients.search.client import FIELD_OZ, FIELD_STL_NR
from shared.config import settings
from shared.models.lv_item import LVItem
from shared.repositories.lv_items import LVItemRepository
from shared.services.retrieval.rrf import reciprocal_rank_fusion

# Keyword fields an exact query is matched against and surfaced ahead of the fused text search.
LV_KEYWORD_FIELDS = (FIELD_OZ, FIELD_STL_NR)


class LVItemSearchService:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        embeddings: EmbeddingsClient,
        search: SearchClient,
    ) -> None:
        self._engine = engine
        self._embeddings = embeddings
        self._search = search

    async def search(self, project_uuid: UUID, query: str, *, limit: int) -> list[LVItem]:
        """The project's LV items matching the query, in relevance order (empty for a blank query).

        Exact oz/stl_nr matches lead, followed by the reciprocal-rank fusion of dense kNN and BM25
        lexical search over the project's LV_ITEM chunks."""
        text = query.strip()
        if not text:
            return []

        scope = lv_items_filter(project_uuid)
        # Retrieve a larger candidate pool than the result limit: an item spans several chunks, so
        # collapsing to distinct items yields fewer rows than chunks retrieved.
        candidate_k = max(2 * limit, settings.retriever_candidate_k)
        [vector] = await self._embeddings.embed([text], project_uuid=project_uuid)

        exact = await self._search.keyword_search(
            text, scope, LV_KEYWORD_FIELDS, size=candidate_k
        )
        dense = await self._search.knn_search(vector, scope, k=candidate_k)
        lexical = await self._search.lexical_search(text, scope, size=candidate_k)
        fused = reciprocal_rank_fusion({"dense": dense, "lexical": lexical})

        ranked = _distinct_source_uuids(
            [hit.chunk.source_doc_uuid for hit in exact]
            + [chunk.chunk.source_doc_uuid for chunk in fused],
            limit=limit,
        )

        async with self._engine.connect() as conn:
            items = await LVItemRepository(conn).list_by_uuids(ranked)
        # An item's chunks can briefly outlive its row (ES vs DB consistency); drop ids with no row.
        by_uuid = {item.lv_item_uuid: item for item in items}
        return [by_uuid[u] for u in ranked if u in by_uuid]


def _distinct_source_uuids(source_uuids: list[UUID], *, limit: int) -> list[UUID]:
    """First `limit` distinct uuids, preserving order (best rank kept)."""
    ranked: list[UUID] = []
    seen: set[UUID] = set()
    for source_uuid in source_uuids:
        if source_uuid not in seen:
            seen.add(source_uuid)
            ranked.append(source_uuid)
            if len(ranked) >= limit:
                break
    return ranked
