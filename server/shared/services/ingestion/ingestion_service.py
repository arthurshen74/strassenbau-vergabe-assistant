"""Orchestrates document ingestion (INGESTION.md), end to end except job claiming.

`ingest_document` renders one page thumbnail per page, runs the LangChain pipeline (PDF
-> RecursiveCharacterTextSplitter chunks in the parallel vector index), runs the common
extraction stage (PDF -> SourceLine), and simple-chunks every PDF into DOCUMENT chunks.
LV items come exclusively from GAEB files (D83/X83), which take a short path instead:
the file parses deterministically into LVItem rows and LV_ITEM chunks plus the LV-level
texts (Vorbemerkungen, Hinweise) as LVText rows and LV_TEXT chunks (no thumbnails,
source lines, or DOCUMENT chunks). It is called directly with a `document_uuid`; passing
a `job_uuid` enables IngestJobEvent progress logging, and omitting it runs jobless for
isolated testing. The worker loop that claims jobs and drives this service is a separate
step.

The repositories and clients are reached here and in the injected LangchainIngestor; the
extraction, chunking, and GAEB submodules are pure."""

from __future__ import annotations

import asyncio
import time
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
from shared.models.enums import SourceDocType
from shared.models.simple_chunk import NewSimpleChunk
from shared.models.thumbnail import NewThumbnail
from shared.services.ingestion.chunking import (
    ChunkDraft,
    chunk_document,
    chunk_lv_item,
    chunk_lv_text,
)
from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.gaeb import is_gaeb_lv_file, parse_gaeb_lv
from shared.services.ingestion.langchain_pipeline import LangchainIngestor
from shared.services.ingestion.lv.types import LVParseResult
from shared.services.ingestion.progress import (
    IngestEvent,
    IngestPhase,
    log_progress,
    record_event,
)
from shared.services.ingestion.thumbnails import render_thumbnails

UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[UnitOfWork]]
# Sink for granular activity lines (message, phase value). The worker wires this to the
# ActivityWriter, which stamps job/worker/document and persists batches.
ActivityEmit = Callable[[str, str | None], None]

# Cap on the exception text persisted in a failure event (surfaced to the UI).
FAILURE_MESSAGE_LIMIT = 500


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
    lv_texts: int
    lv_chunks: int  # LV_ITEM + LV_TEXT chunks


class IngestionService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        storage: StorageClient,
        search: SearchClient,
        embeddings: EmbeddingsClient,
        langchain_ingestor: LangchainIngestor,
        activity: ActivityEmit | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._search = search
        self._embeddings = embeddings
        self._langchain = langchain_ingestor
        self._activity_emit = activity

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

        if is_gaeb_lv_file(document.file_name):
            self._activity(f"start: {document.file_name} (GAEB)", IngestPhase.INGEST)
            return await self._ingest_gaeb_document(document, job_uuid)
        self._activity(
            f"start: {document.file_name} (PDF, {document.number_of_pages} pages)",
            IngestPhase.INGEST,
        )

        # Track the active phase so a failure event names where it broke; surfaced to
        # the UI.
        phase = IngestPhase.INGEST
        try:
            pdf_bytes = await self._download(document_uuid)

            phase = IngestPhase.THUMBNAILS
            started = time.monotonic()
            self._activity(
                f"rendering {document.number_of_pages} pages", IngestPhase.THUMBNAILS
            )
            thumbnails = await self._generate_thumbnails(document_uuid, pdf_bytes)
            self._activity(
                f"stored {thumbnails} thumbnails, thumbnails done in "
                f"{time.monotonic() - started:.1f} s",
                IngestPhase.THUMBNAILS,
            )
            await self._emit(
                job_uuid,
                event=IngestEvent.THUMBNAILS_GENERATED,
                phase=IngestPhase.THUMBNAILS,
                message=f"{thumbnails} thumbnails",
            )

            phase = IngestPhase.LANGCHAIN
            started = time.monotonic()
            self._activity("running langchain pipeline", IngestPhase.LANGCHAIN)
            langchain_chunks = await self._langchain.ingest(
                document_uuid,
                document.project_uuid,
                pdf_bytes,
                ingest_job_uuid=job_uuid,
                activity=lambda message: self._activity(message, IngestPhase.LANGCHAIN),
            )
            self._activity(
                f"langchain done in {time.monotonic() - started:.1f} s",
                IngestPhase.LANGCHAIN,
            )
            await self._emit(
                job_uuid,
                event=IngestEvent.LANGCHAIN_CHUNKS_INDEXED,
                phase=IngestPhase.LANGCHAIN,
                message=f"{langchain_chunks} langchain chunks",
            )

            phase = IngestPhase.EXTRACT
            started = time.monotonic()
            new_lines = extract_source_lines(pdf_bytes, document_uuid)
            self._activity(
                f"extracted {len(new_lines)} source lines from "
                f"{document.number_of_pages} pages in "
                f"{time.monotonic() - started:.1f} s",
                IngestPhase.EXTRACT,
            )
            async with self._uow_factory() as uow:
                source_lines = await uow.source_lines.add_many(new_lines)
                await self._emit_in_uow(
                    uow,
                    job_uuid,
                    event=IngestEvent.SOURCE_LINES_PERSISTED,
                    phase=IngestPhase.EXTRACT,
                    message=f"{len(source_lines)} source lines",
                )

            phase = IngestPhase.CHUNK
            started = time.monotonic()
            doc_drafts = chunk_document(
                source_lines,
                project_uuid=document.project_uuid,
                document_uuid=document_uuid,
            )
            self._activity(f"{len(doc_drafts)} chunks drafted", IngestPhase.CHUNK)
            document_chunks = await self._embed_and_index(
                doc_drafts,
                document_uuid,
                SourceDocType.DOCUMENT,
                document.project_uuid,
                job_uuid,
                document_uuid,
            )
            self._activity(
                f"chunks done in {time.monotonic() - started:.1f} s", IngestPhase.CHUNK
            )
            await self._emit(
                job_uuid,
                event=IngestEvent.DOCUMENT_CHUNKS_INDEXED,
                phase=IngestPhase.CHUNK,
                message=f"{document_chunks} document chunks",
            )
        except Exception as exc:
            self._activity_failure(exc, phase)
            await self._emit(
                job_uuid,
                event=IngestEvent.FAILED,
                phase=phase,
                message=str(exc)[:FAILURE_MESSAGE_LIMIT],
            )
            raise

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
            lv_items=0,
            lv_texts=0,
            lv_chunks=0,
        )

    async def _ingest_gaeb_document(
        self, document: Document, job_uuid: UUID | None
    ) -> IngestionResult:
        """GAEB short path: parse the D83/X83 file into LV items and LV texts and
        persist/index them. There are no pages, so thumbnails, source lines, and
        DOCUMENT chunks are skipped entirely."""
        try:
            raw_bytes = await self._download(document.document_uuid)
            self._activity("parsing GAEB LV", IngestPhase.LV)
            result = parse_gaeb_lv(document.file_name, raw_bytes)
            self._activity(
                f"parsed {len(result.items)} items, {len(result.add_texts)} texts, "
                f"{len(result.remarks)} remarks",
                IngestPhase.LV,
            )
            lv_items, lv_texts, lv_chunks = await self._persist_lv_result(
                document, result, job_uuid
            )
            await self._emit(
                job_uuid,
                event=IngestEvent.LV_ITEMS_INDEXED,
                phase=IngestPhase.LV,
                message=f"{lv_items} LV items, {lv_texts} LV texts, {lv_chunks} chunks",
            )
        except Exception as exc:
            self._activity_failure(exc, IngestPhase.LV)
            await self._emit(
                job_uuid,
                event=IngestEvent.FAILED,
                phase=IngestPhase.LV,
                message=str(exc)[:FAILURE_MESSAGE_LIMIT],
            )
            raise

        await self._emit(
            job_uuid,
            event=IngestEvent.COMPLETED,
            phase=IngestPhase.INGEST,
            message="ingestion complete",
        )
        return IngestionResult(
            source_lines=0,
            thumbnails=0,
            langchain_chunks=0,
            document_chunks=0,
            lv_items=lv_items,
            lv_texts=lv_texts,
            lv_chunks=lv_chunks,
        )

    async def _persist_lv_result(
        self, document: Document, result: LVParseResult, job_uuid: UUID | None
    ) -> tuple[int, int, int]:
        """Persist and index the parse: returns (lv_items, lv_texts, chunks)."""
        pages_by_oz = {item.oz: item.pages for item in result.items}
        new_ozs = [item.oz for item in result.items]

        # Upsert the parsed items (stable uuids) and drop any position that no longer
        # exists, so a re-ingest neither collides on (document_uuid, oz) nor leaves
        # stale rows. LV texts have no natural key and are replaced wholesale.
        async with self._uow_factory() as uow:
            items = await uow.lv_items.add_many(
                result.to_new_lv_items(document.document_uuid)
            )
            removed = await uow.lv_items.delete_missing(document.document_uuid, new_ozs)
            texts, removed_texts = await uow.lv_texts.replace(
                document.document_uuid, result.to_new_lv_texts(document.document_uuid)
            )
        self._activity(
            f"removed {len(removed)} stale positions, {len(removed_texts)} stale texts",
            IngestPhase.LV,
        )

        # Archive the Elasticsearch chunks of the removed positions and texts; the
        # surviving items' prior chunks are archived per item below before re-indexing
        # (their uuids are unchanged).
        for removed_uuid in removed:
            await self._search.archive_source(removed_uuid, SourceDocType.LV_ITEM)
        for removed_uuid in removed_texts:
            await self._search.archive_source(removed_uuid, SourceDocType.LV_TEXT)

        lv_chunks = 0
        for index, item in enumerate(items, start=1):
            drafts = chunk_lv_item(
                item, pages_by_oz.get(item.oz, []), project_uuid=document.project_uuid
            )
            lv_chunks += await self._embed_and_index(
                drafts,
                item.lv_item_uuid,
                SourceDocType.LV_ITEM,
                document.project_uuid,
                job_uuid,
                document.document_uuid,
            )
            if index % settings.activity_lv_item_every == 0:
                self._activity(
                    f"LV item {item.oz} ({index}/{len(items)})", IngestPhase.LV
                )
        for text in texts:
            lv_chunks += await self._embed_and_index(
                chunk_lv_text(text, project_uuid=document.project_uuid),
                text.lv_text_uuid,
                SourceDocType.LV_TEXT,
                document.project_uuid,
                job_uuid,
                document.document_uuid,
            )
        if texts:
            self._activity(f"{len(texts)} LV texts indexed", IngestPhase.LV)
        return len(items), len(texts), lv_chunks

    async def _generate_thumbnails(self, document_uuid: UUID, pdf_bytes: bytes) -> int:
        """Render one thumbnail per page, store each in object storage, and upsert a
        Thumbnail row per page (keyed by (document_uuid, page_number), so re-ingest
        replaces in place). Rendering and the synchronous storage writes are offloaded
        to threads."""
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
            if page.page_number % settings.activity_thumbnail_every == 0:
                self._activity(
                    f"rendered thumbnail {page.page_number}/{len(rendered)}",
                    IngestPhase.THUMBNAILS,
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
        document_uuid: UUID,
    ) -> int:
        """Embed the drafts, archive the source's prior chunks, then index the new ones.
        The owning document_uuid (distinct from source_doc_uuid, which is the lv_item
        or lv_text for LV chunks) tags the embeddings' OpenRouter usage."""
        if not drafts:
            return 0
        vectors = await self._embeddings.embed(
            [draft.chunk_text for draft in drafts],
            project_uuid=project_uuid,
            ingest_job_uuid=job_uuid,
            document_uuid=document_uuid,
        )
        activity_phase = (
            IngestPhase.CHUNK
            if source_doc_type is SourceDocType.DOCUMENT
            else IngestPhase.LV
        )
        chunks: list[NewSimpleChunk] = []
        for index, (draft, vector) in enumerate(zip(drafts, vectors), start=1):
            chunks.append(
                NewSimpleChunk(
                    **draft.model_dump(),
                    embedding=vector,
                    embedding_model=settings.embedding_model,
                )
            )
            if index % settings.activity_embed_every == 0:
                self._activity(f"embedded {index}/{len(drafts)} chunks", activity_phase)
        await self._search.archive_source(source_doc_uuid, source_doc_type)
        # LV items index one small batch each; only the document batch gets lines.
        if source_doc_type is SourceDocType.DOCUMENT:
            self._activity("archived previous chunks", activity_phase)
        await self._search.index_chunks(chunks)
        if source_doc_type is SourceDocType.DOCUMENT:
            self._activity(
                f"indexed {len(chunks)} chunks into {settings.elasticsearch_index}",
                activity_phase,
            )
        return len(chunks)

    async def _download(self, document_uuid: UUID) -> bytes:
        """Read the raw upload from object storage."""
        self._activity("downloading from storage", IngestPhase.INGEST)
        started = time.monotonic()
        data = await asyncio.to_thread(
            self._storage.get_object, raw_object_key(document_uuid)
        )
        self._activity(
            f"downloaded {len(data) / 1024:.0f} KB ({len(data)} bytes) in "
            f"{time.monotonic() - started:.1f} s",
            IngestPhase.INGEST,
        )
        return data

    async def _emit(
        self,
        job_uuid: UUID | None,
        *,
        event: IngestEvent,
        phase: IngestPhase,
        message: str,
    ) -> None:
        """Log progress to stdout (always) and persist it in its own transaction when
        there is a job; jobless runs only log."""
        log_progress(event=event, phase=phase, message=message)
        if job_uuid is None:
            return
        async with self._uow_factory() as uow:
            await record_event(
                uow.ingest_job_events,
                job_uuid,
                event=event,
                phase=phase,
                message=message,
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
        """Log progress to stdout and persist it within an already-open transaction (so
        the event commits atomically with that stage's writes)."""
        log_progress(event=event, phase=phase, message=message)
        await record_event(
            uow.ingest_job_events, job_uuid, event=event, phase=phase, message=message
        )

    def _activity_failure(self, exc: Exception, phase: IngestPhase) -> None:
        message = str(exc)[:FAILURE_MESSAGE_LIMIT]
        self._activity(f"failed: {type(exc).__name__}: {message}", phase)

    def _activity(self, message: str, phase: IngestPhase) -> None:
        """Emit a granular activity line for the live console and the worker's lease
        heartbeat. No-op for jobless runs, which have no activity sink wired."""
        if self._activity_emit is not None:
            self._activity_emit(message, phase.value)
