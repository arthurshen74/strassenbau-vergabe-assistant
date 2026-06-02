"""The LangChain ingestion step: PDF bytes to vectors in the `idx-langchain-roadbuilders` index.

Runs between thumbnail generation and Poppler source-line extraction, in parallel to (and
independent of) the SimpleChunk pipeline. It writes the raw PDF to a temp file, loads it with
PyPDFLoader, splits the pages with RecursiveCharacterTextSplitter, stamps each chunk with the
project / source-document metadata, replaces the document's prior vectors (so a re-ingest does not
duplicate them), and indexes the chunks via ElasticsearchStore. PyPDFLoader, the splitter, and the
store are synchronous, so the work runs inside `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from uuid import UUID

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from shared.clients.search.langchain_store import (
    META_PROJECT_UUID,
    META_SOURCE_DOC_TYPE,
    META_SOURCE_DOC_UUID,
    build_elasticsearch_client,
    build_langchain_embeddings,
    build_langchain_vector_store,
)
from shared.config import settings
from shared.models.enums import SourceDocType

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# PyPDFLoader records the temp file path under this key; overwrite it so the path does not leak.
META_SOURCE = "source"


class LangchainIngestor:
    """Loads, splits, embeds, and indexes a PDF into the LangChain vector store."""

    def __init__(self) -> None:
        self._client = build_elasticsearch_client()
        self._vector_store = build_langchain_vector_store(
            build_langchain_embeddings(), self._client
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
        )

    async def ingest(self, document_uuid: UUID, project_uuid: UUID, pdf_bytes: bytes) -> int:
        """Index the PDF's chunks and return the chunk count."""
        return await asyncio.to_thread(
            self._ingest_sync, document_uuid, project_uuid, pdf_bytes
        )

    def _ingest_sync(self, document_uuid: UUID, project_uuid: UUID, pdf_bytes: bytes) -> int:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(pdf_bytes)
            tmp.close()
            pages = PyPDFLoader(tmp.name).load()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

        chunks = self._splitter.split_documents(pages)
        if not chunks:
            return 0
        for chunk in chunks:
            chunk.metadata[META_PROJECT_UUID] = str(project_uuid)
            chunk.metadata[META_SOURCE_DOC_UUID] = str(document_uuid)
            chunk.metadata[META_SOURCE_DOC_TYPE] = SourceDocType.DOCUMENT.value
            chunk.metadata[META_SOURCE] = str(document_uuid)

        # Replace the document's prior vectors so a re-ingest does not duplicate them; the index
        # may not exist yet on the first run.
        self._client.delete_by_query(
            index=settings.langchain_index,
            query={"term": {f"metadata.{META_SOURCE_DOC_UUID}": str(document_uuid)}},
            ignore_unavailable=True,
            conflicts="proceed",
            refresh=True,
        )
        added = self._vector_store.add_documents(chunks)
        return len(added)

    def close(self) -> None:
        self._client.close()
