from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.graph.models import ChunkType


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    score: float


class SearchClient:
    """BM25 over the single global `roadbuilders_text` index (`settings.elasticsearch_index`),
    the only caller of the Elasticsearch client. The index is derived/rebuildable from Neo4j.
    German analyzer; every query MUST filter `project_uuid`. Deterministic `_id`s make
    indexing idempotent: `"lv_item:{document_id}:{oz}"` and `"chunk:{chunk_id}"`. Wraps the
    async `elasticsearch` client. See docs/DATA_MODEL.md §8.
    """

    async def bootstrap_index(self) -> None:
        """Create `roadbuilders_text` (german analyzer + mapping); no-op if it exists."""
        raise NotImplementedError

    async def index_lv_item(
        self,
        *,
        document_id: str,
        oz: str,
        project_uuid: str,
        text: str,
        text_raw: str,
    ) -> None:
        raise NotImplementedError

    async def index_chunk(
        self,
        *,
        chunk_id: str,
        chunk_type: ChunkType,
        document_id: str,
        project_uuid: str,
        text: str,
    ) -> None:
        raise NotImplementedError

    async def delete_by_document_id(self, document_id: str) -> None:
        """`delete_by_query` on `document_id` (clean re-ingest)."""
        raise NotImplementedError

    async def search(
        self,
        *,
        project_uuid: str,
        query: str,
        kind: str | None = None,
        chunk_type: ChunkType | None = None,
        top_k: int = 20,
    ) -> list[SearchHit]:
        """`kind` filters `lv_item` | `chunk`; `chunk_type` selects the `simple`/`prose` arm."""
        raise NotImplementedError
