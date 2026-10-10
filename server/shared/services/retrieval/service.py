"""The retrieval orchestrator (RETRIEVAL.md).

RetrievalService runs one scoped RAG retrieval: it resolves the Simple/Plus scope,
optionally expands the query into variants, runs dense (and optionally BM25) search per
query, fuses the ranked lists with reciprocal rank fusion, optionally reranks with the
cross-encoder, and answers from the top-k context using the project_chat prompt. It
returns a RetrievalResult that captures every stage and emits no logs of its own; the
caller (the debug CLI) prints the trace, so logging stays at the boundary. DB reads use
short connections, mirroring the Dispatcher idiom.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search import ScoredChunk, SearchClient, plus_filter, simple_filter
from shared.models.chat_message import ChatMessage
from shared.models.enums import PromptType, RetrievalModality, SourceDocType
from shared.models.simple_chunk import SimpleChunk
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.prompt_runner import PromptRunner
from shared.services.retrieval.config import RetrievalConfig
from shared.services.retrieval.models import (
    ContextChunk,
    FusedTrace,
    HitTrace,
    QueryTrace,
    RerankTrace,
    RetrievalContext,
    RetrievalResult,
    ScopeTrace,
    ThumbnailRef,
)
from shared.services.retrieval.rrf import FusedChunk, reciprocal_rank_fusion

# The {{placeholder}} the project_chat prompt expects the numbered evidence under.
VARIABLE_CONTEXT = "context"

# Characters of chunk_text kept in the trace previews (full text only in ContextChunk).
PREVIEW_LENGTH = 160

# Hex characters of a uuid shown in a context source header.
UUID_ABBREV_LENGTH = 8

_tracer = trace.get_tracer(__name__)


class RetrievalService:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        llm: LLMClient,
        embeddings: EmbeddingsClient,
        search: SearchClient,
        reranker: RerankClient,
    ) -> None:
        self._engine = engine
        self._llm = llm
        self._embeddings = embeddings
        self._search = search
        self._reranker = reranker

    async def retrieve(
        self, question: str, project_uuid: UUID, config: RetrievalConfig
    ) -> RetrievalResult:
        ctx = await self.retrieve_context(question, project_uuid, config)
        answer = await self._answer(question, ctx.context, project_uuid)
        return RetrievalResult(
            config=ctx.config,
            question=ctx.question,
            scope=ctx.scope,
            queries=ctx.queries,
            fused=ctx.fused,
            reranked=ctx.reranked,
            context=ctx.context,
            rrf_applied=ctx.rrf_applied,
            rerank_applied=ctx.rerank_applied,
            answer=answer,
        )

    async def retrieve_context(
        self,
        question: str,
        project_uuid: UUID,
        config: RetrievalConfig,
        *,
        scope_override: dict[str, Any] | None = None,
        conversation_uuid: UUID | None = None,
    ) -> RetrievalContext:
        # Own span so the native elasticsearch-py query spans nest under a labeled
        # retrieval span:
        # they cannot nest under the LangChain tool span (see
        # shared.clients.tracing.flow_span).
        with _tracer.start_as_current_span("retrieval.retrieve_context") as span:
            span.set_attribute("retrieval.modality", config.modality.value)
            span.set_attribute("retrieval.project_uuid", str(project_uuid))
            span.set_attribute("retrieval.scoped", scope_override is not None)
            result = await self._retrieve_context(
                question,
                project_uuid,
                config,
                scope_override=scope_override,
                conversation_uuid=conversation_uuid,
            )
            span.set_attribute("retrieval.result_chunks", len(result.context))
            return result

    async def _retrieve_context(
        self,
        question: str,
        project_uuid: UUID,
        config: RetrievalConfig,
        *,
        scope_override: dict[str, Any] | None = None,
        conversation_uuid: UUID | None = None,
    ) -> RetrievalContext:
        """The full pipeline up to the numbered context, without generating an answer.

        `scope_override` substitutes a caller-built ES filter for the Simple/Plus scope
        (e.g. the agent's LV-only `get_lv_context`); the rest of the pipeline is
        unchanged."""
        es_filter = (
            scope_override
            if scope_override is not None
            else _resolve_scope(project_uuid, config)
        )
        scope = ScopeTrace(
            modality=config.modality, project_uuid=project_uuid, es_filter=es_filter
        )

        query_texts = await self._build_query_texts(
            question, project_uuid, config, conversation_uuid
        )
        vectors = await self._embeddings.embed(
            query_texts, project_uuid=project_uuid, conversation_uuid=conversation_uuid
        )

        query_traces: list[QueryTrace] = []
        ranked_lists: dict[str, Sequence[ScoredChunk]] = {}
        for i, (text, vector) in enumerate(zip(query_texts, vectors)):
            dense = await self._search.knn_search(
                vector, es_filter, k=config.candidate_k
            )
            lexical = (
                await self._search.lexical_search(
                    text, es_filter, size=config.candidate_k
                )
                if config.use_bm25
                else []
            )
            ranked_lists[f"q{i}:dense"] = dense
            if config.use_bm25:
                ranked_lists[f"q{i}:lexical"] = lexical
            query_traces.append(
                QueryTrace(
                    query_text=text,
                    is_original=i == 0,
                    dense_hits=[_hit_trace(h) for h in dense],
                    lexical_hits=[_hit_trace(h) for h in lexical],
                )
            )

        fused = reciprocal_rank_fusion(ranked_lists, top_n=config.candidate_k)
        rrf_applied = len(ranked_lists) > 1

        final_chunks, rerank_traces, rerank_applied = await self._select_context(
            question, fused, project_uuid, config, conversation_uuid
        )
        context = [_context_chunk(i + 1, chunk) for i, chunk in enumerate(final_chunks)]

        return RetrievalContext(
            config=config,
            question=question,
            scope=scope,
            queries=query_traces,
            fused=[_fused_trace(f) for f in fused],
            reranked=rerank_traces,
            context=context,
            rrf_applied=rrf_applied,
            rerank_applied=rerank_applied,
        )

    async def _build_query_texts(
        self,
        question: str,
        project_uuid: UUID,
        config: RetrievalConfig,
        conversation_uuid: UUID | None = None,
    ) -> list[str]:
        if not config.multi_query:
            return [question]
        async with self._engine.connect() as conn:
            runner = PromptRunner(PromptVersionRepository(conn), self._llm)
            variants = await runner.generate_query_variants(
                question,
                n=config.multi_query_n,
                project_uuid=project_uuid,
                conversation_uuid=conversation_uuid,
            )
        return [question, *variants]

    async def _select_context(
        self,
        question: str,
        fused: list[FusedChunk],
        project_uuid: UUID,
        config: RetrievalConfig,
        conversation_uuid: UUID | None = None,
    ) -> tuple[list[SimpleChunk], list[RerankTrace], bool]:
        if not config.use_cross_encoder:
            return [f.chunk for f in fused[: config.top_k]], [], False
        documents = [f.chunk.chunk_text for f in fused]
        ranked = await self._reranker.rerank(
            question,
            documents,
            top_n=config.top_k,
            project_uuid=project_uuid,
            conversation_uuid=conversation_uuid,
        )
        final_chunks = [fused[index].chunk for index, _ in ranked]
        rerank_traces = [
            RerankTrace(
                chunk_uuid=fused[index].chunk.chunk_uuid,
                relevance_score=score,
                rank=position + 1,
            )
            for position, (index, score) in enumerate(ranked)
        ]
        return final_chunks, rerank_traces, True

    async def _answer(
        self, question: str, context: list[ContextChunk], project_uuid: UUID
    ) -> str:
        context_block = format_context(context)
        async with self._engine.connect() as conn:
            runner = PromptRunner(PromptVersionRepository(conn), self._llm)
            return await runner.run_text(
                PromptType.PROJECT_CHAT,
                messages=[ChatMessage(role="user", content=question)],
                variables={VARIABLE_CONTEXT: context_block},
                project_uuid=project_uuid,
            )


def _resolve_scope(project_uuid: UUID, config: RetrievalConfig) -> dict[str, Any]:
    if config.modality is RetrievalModality.SIMPLE:
        return simple_filter(project_uuid)
    return plus_filter(project_uuid)


def _preview(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= PREVIEW_LENGTH:
        return collapsed
    return collapsed[:PREVIEW_LENGTH].rstrip() + "..."


def _hit_trace(scored: ScoredChunk) -> HitTrace:
    chunk = scored.chunk
    return HitTrace(
        chunk_uuid=chunk.chunk_uuid,
        score=scored.score,
        source_doc_type=chunk.source_doc_type,
        source_doc_uuid=chunk.source_doc_uuid,
        oz=chunk.oz,
        source_doc_pages=chunk.source_doc_pages,
        text_preview=_preview(chunk.chunk_text),
    )


def _fused_trace(fused: FusedChunk) -> FusedTrace:
    chunk = fused.chunk
    return FusedTrace(
        chunk_uuid=chunk.chunk_uuid,
        rrf_score=fused.rrf_score,
        contributing_ranks=fused.contributing_ranks,
        oz=chunk.oz,
        source_doc_uuid=chunk.source_doc_uuid,
        text_preview=_preview(chunk.chunk_text),
    )


def _context_chunk(source_number: int, chunk: SimpleChunk) -> ContextChunk:
    return ContextChunk(
        source_number=source_number,
        chunk_uuid=chunk.chunk_uuid,
        source_doc_type=chunk.source_doc_type,
        source_doc_uuid=chunk.source_doc_uuid,
        oz=chunk.oz,
        stl_nr=chunk.stl_nr,
        source_doc_pages=chunk.source_doc_pages,
        chunk_text=chunk.chunk_text,
        thumbnail=_thumbnail_ref(chunk),
    )


def _thumbnail_ref(chunk: SimpleChunk) -> ThumbnailRef | None:
    """The first-page thumbnail of a DOCUMENT chunk's own document. LV_ITEM and
    LV_TEXT chunks come from GAEB files, which have no pages, so they get none."""
    if (
        chunk.source_doc_type is not SourceDocType.DOCUMENT
        or not chunk.source_doc_pages
    ):
        return None
    return ThumbnailRef(
        document_uuid=chunk.source_doc_uuid, page_number=chunk.source_doc_pages[0]
    )


def _format_pages(pages: list[int]) -> str:
    if not pages:
        return "pages n/a"
    ordered = sorted(set(pages))
    if len(ordered) == 1:
        return f"page {ordered[0]}"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"pages {ordered[0]}-{ordered[-1]}"
    return "pages " + ", ".join(str(p) for p in ordered)


def _source_header(chunk: ContextChunk) -> str:
    parts = [chunk.source_doc_type.value]
    if chunk.oz:
        parts.append(f"OZ {chunk.oz}")
    if chunk.stl_nr:
        parts.append(f"STL {chunk.stl_nr}")
    parts.append(f"doc {str(chunk.source_doc_uuid)[:UUID_ABBREV_LENGTH]}")
    parts.append(_format_pages(chunk.source_doc_pages))
    return f"[{chunk.source_number}] ({', '.join(parts)})"


def format_context(context: list[ContextChunk]) -> str:
    """Render the numbered evidence block the project_chat answer prompt expects under
    {{context}}."""
    return "\n\n".join(f"{_source_header(c)}\n{c.chunk_text}" for c in context)
