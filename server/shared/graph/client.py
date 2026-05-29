from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.graph.models import (
    Document,
    LVItem,
    Page,
    Project,
    ProseChunk,
    Section,
    SimpleChunk,
)


class GraphHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    score: float


class GraphClient:
    """Neo4j client: the only writer of the construction graph and the semantic-search
    channel. Wraps the async `neo4j` driver. Node upserts use MERGE on the natural key
    (docs/DATA_MODEL.md §7.4); every query filters `project_uuid`. Vectors are stored on
    the node `embedding` property and queried via native per-label vector indexes at
    `settings.embedding_dim`. Edge writers (HAS_*, CHILD_OF, NEXT_*/PREV_*, SOURCED_FROM)
    accompany the node merges; their exact shape is finalised by the ingest tasks.

    `GraphHit.id` is the unified id space shared with the BM25 channel:
    `"lv_item:{document_id}:{oz}"` or `"chunk:{chunk_id}"`.
    """

    async def bootstrap(self) -> None:
        """Create uniqueness constraints, property indexes, and per-label vector indexes."""
        raise NotImplementedError

    async def merge_project(self, project: Project) -> None:
        raise NotImplementedError

    async def merge_document(self, document: Document) -> None:
        raise NotImplementedError

    async def merge_page(self, page: Page) -> None:
        raise NotImplementedError

    async def merge_section(self, section: Section) -> None:
        raise NotImplementedError

    async def merge_lv_item(self, item: LVItem) -> None:
        raise NotImplementedError

    async def merge_chunk(self, chunk: SimpleChunk | ProseChunk) -> None:
        raise NotImplementedError

    async def vector_search(
        self,
        *,
        label: str,
        embedding: list[float],
        project_uuid: UUID,
        top_k: int = 20,
    ) -> list[GraphHit]:
        """Query one label's vector index (LVItem | SimpleChunk | ProseChunk), scoped to
        project_uuid; returns hits in the unified id space."""
        raise NotImplementedError
