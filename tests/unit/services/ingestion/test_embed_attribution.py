"""Guard that SimpleChunk embedding usage is attributed to the owning document.

`_embed_and_index` embeds the drafts and archives the source's prior chunks. For LV chunks the
source is the `lv_item` (its `source_doc_uuid`), but the OpenRouter usage must be tagged with the
owning `document_uuid` instead - the two diverge only on the LV branch, which is exactly where a
regression would go unnoticed."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from shared.models.enums import SourceDocType
from shared.models.simple_chunk import NewSimpleChunk
from shared.services.ingestion.chunking import (
    SOURCE_DOC_FIELD_DOCUMENT,
    SOURCE_DOC_FIELD_LV_ITEM,
    ChunkDraft,
)
from shared.services.ingestion.ingestion_service import IngestionService


class _RecordingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append({"texts": texts, **kwargs})
        return [[float(i)] for i in range(len(texts))]


class _RecordingSearch:
    def __init__(self) -> None:
        self.archived: list[tuple[Any, SourceDocType]] = []
        self.indexed: list[NewSimpleChunk] = []

    async def archive_source(self, source_doc_uuid: Any, source_doc_type: SourceDocType) -> int:
        self.archived.append((source_doc_uuid, source_doc_type))
        return 0

    async def index_chunks(self, chunks: list[NewSimpleChunk]) -> list[Any]:
        self.indexed.extend(chunks)
        return [uuid4() for _ in chunks]


def _service(embeddings: _RecordingEmbeddings, search: _RecordingSearch) -> IngestionService:
    # _embed_and_index touches only the embeddings + search collaborators.
    return IngestionService(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        search,  # type: ignore[arg-type]
        embeddings,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )


async def test_document_chunks_attribute_usage_to_the_document() -> None:
    embeddings, search = _RecordingEmbeddings(), _RecordingSearch()
    service = _service(embeddings, search)
    project_uuid, job_uuid, document_uuid = uuid4(), uuid4(), uuid4()
    drafts = [
        ChunkDraft(
            source_doc_uuid=document_uuid,
            source_doc_type=SourceDocType.DOCUMENT,
            source_doc_field=SOURCE_DOC_FIELD_DOCUMENT,
            source_doc_pages=[1],
            chunk_index=0,
            project_uuid=project_uuid,
            chunk_text="hello",
        )
    ]

    count = await service._embed_and_index(
        drafts, document_uuid, SourceDocType.DOCUMENT, project_uuid, job_uuid, document_uuid
    )

    assert count == 1
    assert embeddings.calls[0]["project_uuid"] == project_uuid
    assert embeddings.calls[0]["ingest_job_uuid"] == job_uuid
    assert embeddings.calls[0]["document_uuid"] == document_uuid


async def test_lv_chunks_attribute_usage_to_owning_document_not_the_lv_item() -> None:
    embeddings, search = _RecordingEmbeddings(), _RecordingSearch()
    service = _service(embeddings, search)
    project_uuid, job_uuid, document_uuid, lv_item_uuid = uuid4(), uuid4(), uuid4(), uuid4()
    drafts = [
        ChunkDraft(
            source_doc_uuid=lv_item_uuid,
            source_doc_type=SourceDocType.LV_ITEM,
            source_doc_field=SOURCE_DOC_FIELD_LV_ITEM,
            source_doc_pages=[2],
            chunk_index=0,
            oz="1.1",
            project_uuid=project_uuid,
            chunk_text="lv text",
        )
    ]

    count = await service._embed_and_index(
        drafts, lv_item_uuid, SourceDocType.LV_ITEM, project_uuid, job_uuid, document_uuid
    )

    assert count == 1
    # Usage attributes to the owning document, not the lv_item that sources the chunk.
    assert embeddings.calls[0]["document_uuid"] == document_uuid
    assert embeddings.calls[0]["document_uuid"] != lv_item_uuid
    # The lv_item is still what gets its prior chunks archived.
    assert search.archived == [(lv_item_uuid, SourceDocType.LV_ITEM)]
