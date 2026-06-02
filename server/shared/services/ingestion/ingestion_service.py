"""Orchestrates document ingestion (INGESTION.md), end to end except job claiming.

`ingest_document` renders one page thumbnail per page, runs the LangChain pipeline (PDF ->
RecursiveCharacterTextSplitter chunks in the parallel vector index), runs the common extraction
stage (PDF -> SourceLine), simple-chunks every document into DOCUMENT chunks, and for an LV
document additionally runs the LV parse into LVItem rows and LV_ITEM chunks. It is called directly
with a `document_uuid`; passing a `job_uuid` enables IngestJobEvent progress logging, and omitting
it runs jobless for isolated testing. The worker loop that claims jobs and drives this service
is a separate step.

The repositories and clients are reached here and in the injected LangchainIngestor; the
extraction, chunking, and LV submodules are pure."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from shared.clients.embeddings.client import EmbeddingsClient
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import (
    StorageClient,
    raw_object_key,
    thumbnail_object_key,
)
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import Document
from shared.models.enums import DocumentType, SourceDocType
from shared.models.simple_chunk import NewSimpleChunk
from shared.models.source_line import SourceLine
from shared.models.thumbnail import NewThumbnail
from shared.services.ingestion.chunking import ChunkDraft, chunk_document, chunk_lv_item
from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.langchain_pipeline import LangchainIngestor
from shared.services.ingestion.lv import postprocess
from shared.services.ingestion.lv.rendering import render_line_numbered
from shared.services.ingestion.progress import (
    IngestEvent,
    IngestPhase,
    log_progress,
    record_event,
)
from shared.services.ingestion.thumbnails import render_thumbnails
from shared.services.prompt_runner import PromptRunner

UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[UnitOfWork]]


class DocumentNotFoundError(Exception):
    """No Document exists for the requested document_uuid."""


@dataclass(frozen=True)
class IngestionResult:
    """Counts produced by one ingest_document run, for assertions and the dev script."""

    source_lines: int
    thumbnails: int
    langchain_chunks: int
    document_chunks: int
    lv_items: int
    lv_chunks: int


class IngestionService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        storage: StorageClient,
        search: SearchClient,
        embeddings: EmbeddingsClient,
        prompts: PromptRunner,
        langchain_ingestor: LangchainIngestor,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._search = search
        self._embeddings = embeddings
        self._prompts = prompts
        self._langchain = langchain_ingestor

    async def ingest_document(
        self, document_uuid: UUID, *, job_uuid: UUID | None = None
    ) -> IngestionResult:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_uuid)
            if document is None:
                raise DocumentNotFoundError(str(document_uuid))
            await self._emit_in_uow(
                uow,
                job_uuid,
                event=IngestEvent.STARTED,
                phase=IngestPhase.INGEST,
                message=document.file_name,
            )

        pdf_bytes = await asyncio.to_thread(
            self._storage.get_object, raw_object_key(document_uuid)
        )

        thumbnails = await self._generate_thumbnails(document_uuid, pdf_bytes)
        await self._emit(
            job_uuid,
            event=IngestEvent.THUMBNAILS_GENERATED,
            phase=IngestPhase.THUMBNAILS,
            message=f"{thumbnails} thumbnails",
        )

        langchain_chunks = await self._langchain.ingest(
            document_uuid, document.project_uuid, pdf_bytes, ingest_job_uuid=job_uuid
        )
        await self._emit(
            job_uuid,
            event=IngestEvent.LANGCHAIN_CHUNKS_INDEXED,
            phase=IngestPhase.LANGCHAIN,
            message=f"{langchain_chunks} langchain chunks",
        )

        new_lines = extract_source_lines(pdf_bytes, document_uuid)
        async with self._uow_factory() as uow:
            source_lines = await uow.source_lines.add_many(new_lines)
            await self._emit_in_uow(
                uow,
                job_uuid,
                event=IngestEvent.SOURCE_LINES_PERSISTED,
                phase=IngestPhase.EXTRACT,
                message=f"{len(source_lines)} source lines",
            )

        doc_drafts = chunk_document(
            source_lines,
            project_uuid=document.project_uuid,
            document_uuid=document_uuid,
        )
        document_chunks = await self._embed_and_index(
            doc_drafts, document_uuid, SourceDocType.DOCUMENT, document.project_uuid, job_uuid
        )
        await self._emit(
            job_uuid,
            event=IngestEvent.DOCUMENT_CHUNKS_INDEXED,
            phase=IngestPhase.CHUNK,
            message=f"{document_chunks} document chunks",
        )

        lv_items = 0
        lv_chunks = 0
        if document.document_type == DocumentType.LV_DOCUMENT:
            lv_items, lv_chunks = await self._ingest_lv(document, source_lines, job_uuid)
            await self._emit(
                job_uuid,
                event=IngestEvent.LV_ITEMS_INDEXED,
                phase=IngestPhase.LV,
                message=f"{lv_items} LV items, {lv_chunks} chunks",
            )

        await self._emit(
            job_uuid,
            event=IngestEvent.COMPLETED,
            phase=IngestPhase.INGEST,
            message="ingestion complete",
        )
        return IngestionResult(
            source_lines=len(source_lines),
            thumbnails=thumbnails,
            langchain_chunks=langchain_chunks,
            document_chunks=document_chunks,
            lv_items=lv_items,
            lv_chunks=lv_chunks,
        )

    async def _ingest_lv(
        self, document: Document, source_lines: list[SourceLine], job_uuid: UUID | None
    ) -> tuple[int, int]:
        rendered, _ = render_line_numbered(source_lines)
        # windowing: see follow-up -- a too-large document overflows this single call.
        extraction = await self._prompts.run_lv_extraction(
            rendered, project_uuid=document.project_uuid, ingest_job_uuid=job_uuid
        )
        result = postprocess.run(extraction, source_lines)
        pages_by_oz = {item.oz: item.pages for item in result.items}
        new_ozs = [item.oz for item in result.items]

        # Upsert the parsed items (stable uuids) and drop any position that no longer exists,
        # so a re-ingest neither collides on (document_uuid, oz) nor leaves stale rows.
        async with self._uow_factory() as uow:
            items = await uow.lv_items.add_many(result.to_new_lv_items(document.document_uuid))
            removed = await uow.lv_items.delete_missing(document.document_uuid, new_ozs)

        # Archive the Elasticsearch chunks of the removed positions; the survivors' prior
        # chunks are archived per item below before re-indexing (their uuids are unchanged).
        for removed_uuid in removed:
            await self._search.archive_source(removed_uuid, SourceDocType.LV_ITEM)

        lv_chunks = 0
        for item in items:
            drafts = chunk_lv_item(
                item, pages_by_oz.get(item.oz, []), project_uuid=document.project_uuid
            )
            lv_chunks += await self._embed_and_index(
                drafts, item.lv_item_uuid, SourceDocType.LV_ITEM, document.project_uuid, job_uuid
            )
        return len(items), lv_chunks

    async def _generate_thumbnails(self, document_uuid: UUID, pdf_bytes: bytes) -> int:
        """Render one thumbnail per page, store each in object storage, and upsert a
        Thumbnail row per page (keyed by (document_uuid, page_number), so re-ingest replaces
        in place). Rendering and the synchronous storage writes are offloaded to threads."""
        rendered = await asyncio.to_thread(render_thumbnails, pdf_bytes)
        if not rendered:
            return 0
        new_thumbnails: list[NewThumbnail] = []
        for page in rendered:
            object_key = thumbnail_object_key(document_uuid, page.page_number)
            await asyncio.to_thread(
                self._storage.put_object, object_key, page.data, page.content_type
            )
            new_thumbnails.append(
                NewThumbnail(
                    document_uuid=document_uuid,
                    page_number=page.page_number,
                    object_key=object_key,
                    bucket=self._storage.bucket,
                    width=page.width,
                    height=page.height,
                    content_type=page.content_type,
                )
            )
        async with self._uow_factory() as uow:
            await uow.thumbnails.add_many(new_thumbnails)
        return len(new_thumbnails)

    async def _embed_and_index(
        self,
        drafts: list[ChunkDraft],
        source_doc_uuid: UUID,
        source_doc_type: SourceDocType,
        project_uuid: UUID,
        job_uuid: UUID | None,
    ) -> int:
        """Embed the drafts, archive the source's prior chunks, then index the new ones."""
        if not drafts:
            return 0
        vectors = await self._embeddings.embed(
            [draft.chunk_text for draft in drafts],
            project_uuid=project_uuid,
            ingest_job_uuid=job_uuid,
        )
        chunks = [
            NewSimpleChunk(
                **draft.model_dump(),
                embedding=vector,
                embedding_model=settings.embedding_model,
            )
            for draft, vector in zip(drafts, vectors)
        ]
        await self._search.archive_source(source_doc_uuid, source_doc_type)
        await self._search.index_chunks(chunks)
        return len(chunks)

    async def _emit(
        self,
        job_uuid: UUID | None,
        *,
        event: IngestEvent,
        phase: IngestPhase,
        message: str,
    ) -> None:
        """Log progress to stdout (always) and persist it in its own transaction when there is
        a job; jobless runs only log."""
        log_progress(event=event, phase=phase, message=message)
        if job_uuid is None:
            return
        async with self._uow_factory() as uow:
            await record_event(
                uow.ingest_job_events, job_uuid, event=event, phase=phase, message=message
            )

    async def _emit_in_uow(
        self,
        uow: UnitOfWork,
        job_uuid: UUID | None,
        *,
        event: IngestEvent,
        phase: IngestPhase,
        message: str,
    ) -> None:
        """Log progress to stdout and persist it within an already-open transaction (so the
        event commits atomically with that stage's writes)."""
        log_progress(event=event, phase=phase, message=message)
        await record_event(
            uow.ingest_job_events, job_uuid, event=event, phase=phase, message=message
        )
