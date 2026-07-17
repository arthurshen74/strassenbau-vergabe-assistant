"""The LangChain ingestion step: PDF bytes to vectors in the
`idx-langchain-roadbuilders` index.

Runs between thumbnail generation and Poppler source-line extraction, in parallel to
(and independent of) the SimpleChunk pipeline. It writes the raw PDF to a temp file,
loads it with PyPDFLoader, splits the pages with RecursiveCharacterTextSplitter, stamps
each chunk with the project / source-document metadata, replaces the document's prior
vectors (so a re-ingest does not duplicate them), and indexes the chunks.

PyPDFLoader, the splitter, and the store are synchronous, so
loading/splitting/deleting/indexing run inside `asyncio.to_thread`. Embedding, however,
goes through the first-party `EmbeddingsClient` on the main event loop (so its usage is
recorded to the DB sink, whose engine is bound to that loop); the precomputed vectors
are then written with `ElasticsearchStore.add_embeddings`.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from uuid import UUID

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from shared.clients.embeddings.client import EmbeddingsClient
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

# PyPDFLoader records the temp file path under this key; overwrite it so the path does
# not leak.
META_SOURCE = "source"


class LangchainIngestor:
    """Loads, splits, embeds, and indexes a PDF into the LangChain vector store."""

    def __init__(self, embeddings: EmbeddingsClient) -> None:
        self._embeddings = embeddings
        self._client = build_elasticsearch_client()
        # The store indexes precomputed vectors via add_embeddings; the embeddings
        # object is only needed to satisfy construction (and serves the retrieval-side
        # similarity_search).
        self._vector_store = build_langchain_vector_store(
            build_langchain_embeddings(), self._client
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
        )

    async def ingest(
        self,
        document_uuid: UUID,
        project_uuid: UUID,
        pdf_bytes: bytes,
        *,
        ingest_job_uuid: UUID | None = None,
    ) -> int:
        """Index the PDF's chunks and return the chunk count."""
        chunks = await asyncio.to_thread(
            self._load_and_split, document_uuid, project_uuid, pdf_bytes
        )
        if not chunks:
            return 0
        await asyncio.to_thread(self._delete_prior_vectors, document_uuid)
        vectors = await self._embeddings.embed(
            [chunk.page_content for chunk in chunks],
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
            document_uuid=document_uuid,
        )
        return await asyncio.to_thread(self._add_vectors, chunks, vectors)

    def _load_and_split(
        self, document_uuid: UUID, project_uuid: UUID, pdf_bytes: bytes
    ) -> list[Document]:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(pdf_bytes)
            tmp.close()
            pages = PyPDFLoader(tmp.name).load()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

        chunks = self._splitter.split_documents(pages)
        for chunk in chunks:
            chunk.metadata[META_PROJECT_UUID] = str(project_uuid)
            chunk.metadata[META_SOURCE_DOC_UUID] = str(document_uuid)
            chunk.metadata[META_SOURCE_DOC_TYPE] = SourceDocType.DOCUMENT.value
            chunk.metadata[META_SOURCE] = str(document_uuid)
        return chunks

    def _delete_prior_vectors(self, document_uuid: UUID) -> None:
        """Replace the document's prior vectors so a re-ingest does not duplicate them;
        the index may not exist yet on the first run."""
        self._client.delete_by_query(
            index=settings.langchain_index,
            query={"term": {f"metadata.{META_SOURCE_DOC_UUID}": str(document_uuid)}},
            ignore_unavailable=True,
            conflicts="proceed",
            refresh=True,
        )

    def _add_vectors(self, chunks: list[Document], vectors: list[list[float]]) -> int:
        text_embeddings = list(zip([chunk.page_content for chunk in chunks], vectors))
        metadatas = [chunk.metadata for chunk in chunks]
        added = self._vector_store.add_embeddings(text_embeddings, metadatas=metadatas)
        return len(added)

    def close(self) -> None:
        self._client.close()
