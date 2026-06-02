"""LangChain Elasticsearch vector store: the contract for the `idx-langchain-roadbuilders` index.

A second, parallel index built by the LangChain ingestion pipeline and read by the LANGCHAIN
retrieval method. It is independent of the SimpleChunk index owned by `SearchClient`: documents are
loaded with PyPDFLoader, split with RecursiveCharacterTextSplitter, embedded with the OpenRouter
`text-embedding-3-small` model, and stored via `ElasticsearchStore`. This module is the single
source of truth for the index name, the chunk metadata keys, the OpenRouter base URL, and the
embeddings / vector-store construction shared by both sides of the contract.
"""

from __future__ import annotations

from elasticsearch import Elasticsearch
from langchain_core.embeddings import Embeddings
from langchain_core.utils import convert_to_secret_str
from langchain_elasticsearch import ElasticsearchStore
from langchain_openai import OpenAIEmbeddings

from shared.config import settings

# OpenRouter's OpenAI-compatible base; the LangChain OpenAI clients append /embeddings and
# /chat/completions themselves, so they take the base rather than the full endpoint URLs.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Chunk metadata keys: written on ingestion and filtered on retrieval. Mapped as `keyword` below
# so `term` filters match `metadata.<key>` directly without a `.keyword` subfield.
META_PROJECT_UUID = "project_uuid"
META_SOURCE_DOC_UUID = "source_doc_uuid"
META_SOURCE_DOC_TYPE = "source_doc_type"

_METADATA_MAPPINGS = {
    META_PROJECT_UUID: {"type": "keyword"},
    META_SOURCE_DOC_UUID: {"type": "keyword"},
    META_SOURCE_DOC_TYPE: {"type": "keyword"},
}


def build_elasticsearch_client() -> Elasticsearch:
    """A synchronous ES client for the LangChain index (used for both the store and delete_by_query).

    Distinct from `SearchClient`'s AsyncElasticsearch: ElasticsearchStore and PyPDFLoader are
    synchronous and run inside `asyncio.to_thread`, so a sync client is the right fit here."""
    return Elasticsearch(settings.elasticsearch_url)


def build_langchain_embeddings() -> OpenAIEmbeddings:
    """OpenRouter embeddings for the LangChain index, matched to the rest of the system.

    `base_url` is required so the call hits OpenRouter rather than api.openai.com;
    `dimensions` mirrors the SimpleChunk vectors; `check_embedding_ctx_length=False` skips the
    tiktoken length probe (the `openai/`-prefixed slug is not a tiktoken model)."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=OPENROUTER_BASE_URL,
        api_key=convert_to_secret_str(settings.openrouter_api_key or ""),
        dimensions=settings.embedding_dim,
        check_embedding_ctx_length=False,
    )


def build_langchain_vector_store(
    embeddings: Embeddings, client: Elasticsearch
) -> ElasticsearchStore:
    """The ElasticsearchStore over `settings.langchain_index`, created on first write."""
    return ElasticsearchStore(
        index_name=settings.langchain_index,
        embedding=embeddings,
        client=client,
        num_dimensions=settings.embedding_dim,
        metadata_mappings=_METADATA_MAPPINGS,
    )
