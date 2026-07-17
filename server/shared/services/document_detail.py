"""Read-side service for the Projects document-detail view.

Assembles a document's header metadata + per-source chunk counts, lists its chunks from
Elasticsearch (SimpleChunk or LangChain index), and lists its ingestion activity across
the active and archive tables. Postgres reads use short read-only connections; chunk
reads go through the shared SearchClient.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.search.client import SearchClient
from shared.models.document_schema import (
    ActivityListRead,
    ChunkListRead,
    ChunkRead,
    DocumentDetailRead,
)
from shared.models.enums import SourceDocType
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_job_events import IngestJobEventRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.services.ingestion.progress import IngestEvent

ChunkSource = Literal["simple", "langchain"]


class DocumentDetailService:
    def __init__(self, engine: AsyncEngine, search: SearchClient) -> None:
        self._engine = engine
        self._search = search

    async def get_detail(
        self, project_uuid: UUID, document_uuid: UUID
    ) -> DocumentDetailRead | None:
        """Header metadata + chunk counts, or None if the document is not in the
        project."""
        async with self._engine.connect() as conn:
            doc = await DocumentRepository(conn).get(document_uuid)
            if doc is None or doc.project_uuid != project_uuid:
                return None
            lv_item_uuids = await LVItemRepository(conn).list_uuids_by_document(
                document_uuid
            )
            last_ingest = await IngestJobEventRepository(conn).latest_event_ts(
                document_uuid, IngestEvent.COMPLETED.value
            )
            ingestion_cost = await OpenRouterUsageRepository(conn).sum_cost_by_document(
                document_uuid
            )
        simple_count = await self._search.count_document_chunks(
            project_uuid, document_uuid, lv_item_uuids
        )
        langchain_count = await self._search.count_langchain_chunks(document_uuid)
        return DocumentDetailRead(
            document_uuid=doc.document_uuid,
            file_name=doc.file_name,
            document_type=doc.document_type,
            number_of_pages=doc.number_of_pages,
            upload_date=doc.created_at,
            last_ingest_date=last_ingest,
            simple_chunk_count=simple_count,
            langchain_chunk_count=langchain_count,
            ingestion_cost=ingestion_cost,
        )

    async def list_chunks(
        self,
        project_uuid: UUID,
        document_uuid: UUID,
        *,
        source: ChunkSource,
        source_doc_type: SourceDocType | None = None,
        text: str | None = None,
        offset: int = 0,
        size: int = 50,
    ) -> ChunkListRead:
        """A page of the document's chunks from the chosen index, plus the total."""
        if source == "langchain":
            items, total = await self._search.list_langchain_chunks(
                document_uuid, text=text, offset=offset, size=size
            )
            return ChunkListRead(
                items=[
                    ChunkRead(
                        chunk_id=c.chunk_id,
                        source="langchain",
                        page=c.page,
                        text=c.text,
                    )
                    for c in items
                ],
                total=total,
            )
        async with self._engine.connect() as conn:
            lv_item_uuids = await LVItemRepository(conn).list_uuids_by_document(
                document_uuid
            )
        views, total = await self._search.list_document_chunks(
            project_uuid,
            document_uuid,
            lv_item_uuids,
            source_doc_type=source_doc_type,
            text=text,
            offset=offset,
            size=size,
        )
        return ChunkListRead(
            items=[
                ChunkRead(
                    chunk_id=v.chunk_uuid,
                    source="simple",
                    source_doc_type=v.source_doc_type,
                    chunk_index=v.chunk_index,
                    oz=v.oz,
                    stl_nr=v.stl_nr,
                    pages=v.source_doc_pages,
                    text=v.chunk_text,
                )
                for v in views
            ],
            total=total,
        )

    async def list_activity(
        self, document_uuid: UUID, *, offset: int = 0, limit: int = 200
    ) -> ActivityListRead:
        """A page of the document's ingestion activity (active ∪ archive) plus the
        total."""
        async with self._engine.connect() as conn:
            repo = IngestionActivityLogRepository(conn)
            items = await repo.list_for_document(
                document_uuid, offset=offset, limit=limit
            )
            total = await repo.count_for_document(document_uuid)
        return ActivityListRead(items=items, total=total)
