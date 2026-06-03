"""Elasticsearch client for the SimpleChunk index.

The single writer and reader of the `SimpleChunk` index. It owns the index mapping,
bulk indexing, the Simple/Plus retrieval scope filters (RETRIEVAL.md), the dense kNN
and BM25 lexical queries built over those filters, and the re-ingestion archival flow
(INGESTION.md). RRF fusion and cross-encoder reranking are the retrieval phase's
concern, not this client's.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from pydantic import BaseModel, ConfigDict

from shared.config import settings
from shared.models.enums import SourceDocType
from shared.models.simple_chunk import NewSimpleChunk, SimpleChunk

# ES field names: one source of truth across mapping, indexing, and query builders.
FIELD_PROJECT_UUID = "project_uuid"
FIELD_SOURCE_DOC_UUID = "source_doc_uuid"
FIELD_SOURCE_DOC_TYPE = "source_doc_type"
FIELD_SOURCE_DOC_FIELD = "source_doc_field"
FIELD_SOURCE_DOC_LANGUAGE = "source_doc_language"
FIELD_SOURCE_DOC_PAGES = "source_doc_pages"
FIELD_CHUNK_INDEX = "chunk_index"
FIELD_OZ = "oz"
FIELD_STL_NR = "stl_nr"
FIELD_CHUNK_TEXT = "chunk_text"
FIELD_EMBEDDING = "embedding"
FIELD_EMBEDDING_MODEL = "embedding_model"
FIELD_ARCHIVED_AT = "archived_at"

# Analyzer / similarity names referenced by the mapping.
GERMAN_ANALYZER = "german"
BM25_SIMILARITY = "BM25"
VECTOR_SIMILARITY = "cosine"

# Async transport: the project standardises on httpx (aiohttp is not a dependency).
NODE_CLASS = "httpxasync"


class ScoredChunk(BaseModel):
    """A search hit: the reconstructed chunk plus its Elasticsearch relevance score."""

    model_config = ConfigDict(extra="forbid")

    chunk: SimpleChunk
    score: float


def _index_mapping() -> dict[str, Any]:
    return {
        "dynamic": "strict",
        "properties": {
            FIELD_PROJECT_UUID: {"type": "keyword"},
            FIELD_SOURCE_DOC_UUID: {"type": "keyword"},
            FIELD_SOURCE_DOC_TYPE: {"type": "keyword"},
            FIELD_SOURCE_DOC_FIELD: {"type": "keyword"},
            FIELD_SOURCE_DOC_LANGUAGE: {"type": "keyword"},
            FIELD_SOURCE_DOC_PAGES: {"type": "integer"},
            FIELD_CHUNK_INDEX: {"type": "integer"},
            FIELD_OZ: {"type": "keyword"},
            FIELD_STL_NR: {"type": "keyword"},
            FIELD_EMBEDDING_MODEL: {"type": "keyword"},
            FIELD_CHUNK_TEXT: {
                "type": "text",
                "analyzer": GERMAN_ANALYZER,
                "similarity": BM25_SIMILARITY,
            },
            FIELD_EMBEDDING: {
                "type": "dense_vector",
                "dims": settings.embedding_dim,
                "index": True,
                "similarity": VECTOR_SIMILARITY,
            },
        },
    }


def _archive_mapping() -> dict[str, Any]:
    mapping = _index_mapping()
    mapping["properties"][FIELD_ARCHIVED_AT] = {"type": "date"}
    return mapping


def simple_filter(project_uuid: UUID) -> dict[str, Any]:
    """Simple scope: project chunks whose source_doc_type is DOCUMENT (RETRIEVAL.md)."""
    return {
        "bool": {
            "filter": [
                {"term": {FIELD_PROJECT_UUID: str(project_uuid)}},
                {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value}},
            ]
        }
    }


def plus_filter(project_uuid: UUID, lv_document_uuid: UUID) -> dict[str, Any]:
    """Plus scope: DOCUMENT chunks except the LV document's own chunks, plus the parsed
    LV_ITEM chunks (RETRIEVAL.md). The LV document's simple chunks are excluded so the LV
    content is not counted twice."""
    return {
        "bool": {
            "filter": [
                {"term": {FIELD_PROJECT_UUID: str(project_uuid)}},
                {
                    "bool": {
                        "minimum_should_match": 1,
                        "should": [
                            {
                                "bool": {
                                    "must": [
                                        {
                                            "term": {
                                                FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value
                                            }
                                        }
                                    ],
                                    "must_not": [
                                        {
                                            "term": {
                                                FIELD_SOURCE_DOC_UUID: str(lv_document_uuid)
                                            }
                                        }
                                    ],
                                }
                            },
                            {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.LV_ITEM.value}},
                        ],
                    }
                },
            ]
        }
    }


def lv_items_filter(project_uuid: UUID) -> dict[str, Any]:
    """LV scope: only the project's parsed LV_ITEM chunks (the structured positions), excluding
    prose DOCUMENT chunks. Backs the agent's get_lv_context tool."""
    return {
        "bool": {
            "filter": [
                {"term": {FIELD_PROJECT_UUID: str(project_uuid)}},
                {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.LV_ITEM.value}},
            ]
        }
    }


def _source_query(source_doc_uuid: UUID, source_doc_type: SourceDocType) -> dict[str, Any]:
    return {
        "bool": {
            "filter": [
                {"term": {FIELD_SOURCE_DOC_UUID: str(source_doc_uuid)}},
                {"term": {FIELD_SOURCE_DOC_TYPE: source_doc_type.value}},
            ]
        }
    }


def _document_footprint_query(
    project_uuid: UUID, document_uuid: UUID, lv_item_uuids: Sequence[UUID]
) -> dict[str, Any]:
    """Every chunk a document put in the index: its own DOCUMENT chunks (keyed by
    document_uuid) and, for an LV document, the LV_ITEM chunks of its parsed items
    (keyed by lv_item_uuid, not document_uuid). Scoped to project_uuid as a guard."""
    should: list[dict[str, Any]] = [
        {
            "bool": {
                "filter": [
                    {"term": {FIELD_SOURCE_DOC_UUID: str(document_uuid)}},
                    {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value}},
                ]
            }
        }
    ]
    if lv_item_uuids:
        should.append(
            {
                "bool": {
                    "filter": [
                        {"terms": {FIELD_SOURCE_DOC_UUID: [str(u) for u in lv_item_uuids]}},
                        {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.LV_ITEM.value}},
                    ]
                }
            }
        )
    return {
        "bool": {
            "filter": [{"term": {FIELD_PROJECT_UUID: str(project_uuid)}}],
            "must": [{"bool": {"minimum_should_match": 1, "should": should}}],
        }
    }


def _hit_to_scored_chunk(hit: dict[str, Any]) -> ScoredChunk:
    chunk = SimpleChunk.model_validate({**hit["_source"], "chunk_uuid": hit["_id"]})
    return ScoredChunk(chunk=chunk, score=hit["_score"])


class SearchClient:
    """Owns the SimpleChunk index lifecycle, indexing, retrieval queries, and archival."""

    def __init__(self, es: AsyncElasticsearch, index: str | None = None) -> None:
        self._es = es
        self._index = index or settings.elasticsearch_index
        self._archive_index = f"{self._index}_archive"

    @classmethod
    def from_settings(cls) -> SearchClient:
        es = AsyncElasticsearch(settings.elasticsearch_url, node_class=NODE_CLASS)
        return cls(es)

    async def close(self) -> None:
        await self._es.close()

    async def ensure_index(self) -> None:
        if not await self._es.indices.exists(index=self._index):
            await self._es.indices.create(index=self._index, mappings=_index_mapping())

    async def _ensure_archive_index(self) -> None:
        if not await self._es.indices.exists(index=self._archive_index):
            await self._es.indices.create(
                index=self._archive_index, mappings=_archive_mapping()
            )

    async def index_chunks(
        self,
        chunks: Sequence[SimpleChunk | NewSimpleChunk],
        *,
        refresh: bool = False,
    ) -> list[UUID]:
        """Bulk-index chunks. A NewSimpleChunk is assigned a fresh chunk_uuid; a
        SimpleChunk keeps its own. The chunk_uuid is the ES document _id. Returns the
        chunk_uuids in input order."""
        assigned: list[UUID] = []
        actions: list[dict[str, Any]] = []
        for chunk in chunks:
            chunk_uuid = chunk.chunk_uuid if isinstance(chunk, SimpleChunk) else uuid4()
            assigned.append(chunk_uuid)
            actions.append(
                {
                    "_index": self._index,
                    "_id": str(chunk_uuid),
                    "_source": chunk.model_dump(mode="json", exclude={"chunk_uuid"}),
                }
            )
        if actions:
            await async_bulk(self._es, actions, refresh=refresh)
        return assigned

    async def knn_search(
        self,
        query_vector: Sequence[float],
        scope_filter: dict[str, Any],
        *,
        k: int = settings.retriever_candidate_k,
        num_candidates: int | None = None,
    ) -> list[ScoredChunk]:
        """Dense kNN over the embedding field, scoped by a Simple/Plus filter."""
        knn = {
            "field": FIELD_EMBEDDING,
            "query_vector": list(query_vector),
            "k": k,
            "num_candidates": num_candidates if num_candidates is not None else max(2 * k, 50),
            "filter": scope_filter,
        }
        resp = await self._es.search(index=self._index, knn=knn, size=k)
        return [_hit_to_scored_chunk(hit) for hit in resp["hits"]["hits"]]

    async def lexical_search(
        self,
        query_text: str,
        scope_filter: dict[str, Any],
        *,
        size: int = settings.retriever_candidate_k,
    ) -> list[ScoredChunk]:
        """BM25 lexical search over chunk_text, scoped by the same Simple/Plus filter."""
        query = {
            "bool": {
                "must": [{"match": {FIELD_CHUNK_TEXT: query_text}}],
                "filter": [scope_filter],
            }
        }
        resp = await self._es.search(index=self._index, query=query, size=size)
        return [_hit_to_scored_chunk(hit) for hit in resp["hits"]["hits"]]

    async def archive_source(
        self, source_doc_uuid: UUID, source_doc_type: SourceDocType
    ) -> int:
        """Re-ingestion archival (INGESTION.md): copy every live chunk matching
        (source_doc_uuid, source_doc_type) into the archive index with an archived_at
        timestamp, then delete them from the live index. Matching the whole source (not
        per chunk_index) means a re-ingest yielding fewer chunks leaves no stale rows.
        Returns the number of chunks removed from the live index."""
        await self._ensure_archive_index()
        query = _source_query(source_doc_uuid, source_doc_type)
        archived_at = datetime.now(tz=timezone.utc).isoformat()
        await self._es.reindex(
            source={"index": self._index, "query": query},
            dest={"index": self._archive_index},
            script={
                "lang": "painless",
                "source": f"ctx._source.{FIELD_ARCHIVED_AT} = params.{FIELD_ARCHIVED_AT}",
                "params": {FIELD_ARCHIVED_AT: archived_at},
            },
            refresh=True,
            wait_for_completion=True,
        )
        deleted = await self._es.delete_by_query(
            index=self._index, query=query, refresh=True
        )
        return int(deleted["deleted"])

    async def archive_and_delete_document(
        self,
        project_uuid: UUID,
        document_uuid: UUID,
        lv_item_uuids: Sequence[UUID],
    ) -> int:
        """Remove a document's whole footprint from the live index: its DOCUMENT chunks
        and, for an LV document, its items' LV_ITEM chunks. Chunks are archived with an
        archived_at timestamp before deletion, matching the re-ingestion flow. Returns
        the number of chunks removed from the live index."""
        await self._ensure_archive_index()
        query = _document_footprint_query(project_uuid, document_uuid, lv_item_uuids)
        archived_at = datetime.now(tz=timezone.utc).isoformat()
        await self._es.reindex(
            source={"index": self._index, "query": query},
            dest={"index": self._archive_index},
            script={
                "lang": "painless",
                "source": f"ctx._source.{FIELD_ARCHIVED_AT} = params.{FIELD_ARCHIVED_AT}",
                "params": {FIELD_ARCHIVED_AT: archived_at},
            },
            refresh=True,
            wait_for_completion=True,
        )
        deleted = await self._es.delete_by_query(
            index=self._index, query=query, refresh=True
        )
        return int(deleted["deleted"])
