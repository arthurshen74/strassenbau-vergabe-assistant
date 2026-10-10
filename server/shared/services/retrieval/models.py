"""The retrieval result and its per-stage trace shapes.

RetrievalService returns one RetrievalResult that captures every stage of the pipeline:
the resolved scope, the query set, per-query hits, the fused candidate pool, the rerank
order, the final numbered context, and the answer. The service builds this and nothing
else; the CLI harness is the only thing that reads and prints it, keeping logging at the
boundary. Embedding vectors are deliberately excluded and hit/fused/rerank views carry a
short text preview so the trace stays readable; ContextChunk keeps the full chunk_text
because that is what the answer was grounded on.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import RetrievalModality, SourceDocType
from shared.services.retrieval.config import RetrievalConfig


class ScopeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: RetrievalModality
    project_uuid: UUID
    es_filter: dict[str, Any]


class HitTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_uuid: UUID
    score: float
    source_doc_type: SourceDocType
    source_doc_uuid: UUID
    oz: str | None = None
    source_doc_pages: list[int]
    text_preview: str


class QueryTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str
    is_original: bool
    dense_hits: list[HitTrace]
    lexical_hits: list[HitTrace] = []


class FusedTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_uuid: UUID
    rrf_score: float
    contributing_ranks: dict[str, int]
    oz: str | None = None
    source_doc_uuid: UUID
    text_preview: str


class RerankTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_uuid: UUID
    relevance_score: float
    rank: int


class ThumbnailRef(BaseModel):
    """Points a DOCUMENT context source at the page thumbnail it came from: the chunk's
    own document and first page. Absent for LV_ITEM / LV_TEXT chunks (GAEB files have no
    pages) and for chunks without a page."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    page_number: int


class ContextChunk(BaseModel):
    """A final-context source, numbered to match the [n] citations in the answer."""

    model_config = ConfigDict(extra="forbid")

    source_number: int
    chunk_uuid: UUID
    source_doc_type: SourceDocType
    source_doc_uuid: UUID
    oz: str | None = None
    stl_nr: str | None = None
    source_doc_pages: list[int]
    chunk_text: str
    thumbnail: ThumbnailRef | None = None


class RetrievalContext(BaseModel):
    """Every retrieval stage except the answer: the scope, query set, per-query hits,
    the fused pool, the rerank order, and the final numbered context. ProjectChatService
    streams the answer itself, so it consumes this; `retrieve()` wraps it with the
    answer into a RetrievalResult."""

    model_config = ConfigDict(extra="forbid")

    config: RetrievalConfig
    question: str
    scope: ScopeTrace
    queries: list[QueryTrace]
    fused: list[FusedTrace]
    reranked: list[RerankTrace] = []
    context: list[ContextChunk]
    rrf_applied: bool
    rerank_applied: bool


class RetrievalResult(RetrievalContext):
    answer: str
