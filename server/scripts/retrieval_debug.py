"""Run a scoped RAG retrieval from the command line and trace every stage to STDOUT.

A thin harness over RetrievalService: it parses a project_uuid and the stage toggles,
bootstraps the clients once, runs the pipeline, and prints the trace. All the logic lives
in shared/services/retrieval; this module only prints.

One-shot (pass --question):

    python -m scripts.retrieval_debug \
      --project <uuid> --question "Welche Anforderungen gelten fuer die Tragschicht?" \
      --modality plus --multi-query --bm25 --cross-encoder

Interactive (omit --question): bootstraps once with the given options, then loops reading
questions from stdin, running each with the same options and printing the trace. Ctrl-D or
'quit' exits. Needs a TTY, so under Docker run without -T:

    docker compose exec worker python -m scripts.retrieval_debug \
      --project <uuid> --modality plus --multi-query --bm25 --cross-encoder

NOTE: PLUS modality and the answer step read the latest seeded prompts. If you edit a
.prompt file, re-run `python -m scripts.seed.prompts` first so get_latest() sees it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from uuid import UUID

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search import SearchClient
from shared.config import settings
from shared.db.engine import make_engine
from shared.models.enums import PromptType, RetrievalModality
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.retrieval import (
    RetrievalConfig,
    RetrievalError,
    RetrievalResult,
    RetrievalService,
)
from shared.services.retrieval.langchain_agent import LangchainRetriever
from shared.services.retrieval.models import HitTrace

SECTION_WIDTH = 64
PREVIEW_LENGTH = 240
UUID_ABBREV_LENGTH = 8


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug a scoped RAG retrieval, tracing to STDOUT.")
    parser.add_argument("--project", type=UUID, required=True, help="project_uuid to scope to")
    parser.add_argument(
        "--question", help="the user question; omit to enter an interactive question loop"
    )
    parser.add_argument(
        "--modality",
        choices=["simple", "plus", "langchain"],
        default="simple",
        help="retrieval scope (langchain runs the agentic RAG path)",
    )
    parser.add_argument(
        "--multi-query",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="expand the query into variants before searching",
    )
    parser.add_argument("--bm25", action="store_true", help="add a BM25 lexical list per query")
    parser.add_argument(
        "--cross-encoder", action="store_true", help="rerank the fused pool with the cross-encoder"
    )
    parser.add_argument("--top-k", type=int, default=settings.retriever_top_k)
    parser.add_argument("--candidate-k", type=int, default=settings.retriever_candidate_k)
    parser.add_argument("--multi-query-n", type=int, default=settings.multi_query_n)
    parser.add_argument(
        "--json", action="store_true", help="dump the full result as JSON instead of a trace"
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if RetrievalModality(args.modality.upper()) is RetrievalModality.LANGCHAIN:
        await _run_langchain(args)
        return
    config = RetrievalConfig(
        modality=RetrievalModality(args.modality.upper()),
        multi_query=args.multi_query,
        use_bm25=args.bm25,
        use_cross_encoder=args.cross_encoder,
        candidate_k=args.candidate_k,
        top_k=args.top_k,
        multi_query_n=args.multi_query_n,
    )

    engine = make_engine(
        settings.database_url, pool_size=2, application_name="retrieval-debug"
    )
    llm = LLMClient()
    embeddings = EmbeddingsClient()
    search = SearchClient.from_settings()
    reranker = RerankClient()
    service = RetrievalService(
        engine=engine, llm=llm, embeddings=embeddings, search=search, reranker=reranker
    )

    try:
        if args.question is not None:
            try:
                await _run_once(service, args.question, args.project, config, args.json)
            except RetrievalError as exc:
                print(f"retrieval error: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
        else:
            await _repl(service, args.project, config, args.json)
    finally:
        await reranker.aclose()
        await embeddings.aclose()
        await llm.aclose()
        await search.close()
        await engine.dispose()


async def _run_langchain(args: argparse.Namespace) -> None:
    """LANGCHAIN modality: build the RAG agent from the latest project_chat prompt and stream it.

    The Simple/Plus stage toggles do not apply here, so they are ignored with a note. The agent's
    chat model and system prompt come from the seeded project_chat prompt version."""
    if args.multi_query or args.bm25 or args.cross_encoder:
        print(
            "note: multi-query / bm25 / cross-encoder are ignored for the langchain modality",
            file=sys.stderr,
        )
    engine = make_engine(settings.database_url, pool_size=2, application_name="retrieval-debug")
    try:
        async with engine.connect() as conn:
            prompt = await PromptVersionRepository(conn).get_latest(PromptType.PROJECT_CHAT)
        if prompt is None:
            print(
                "no project_chat prompt seeded; run `python -m scripts.seed.prompts`",
                file=sys.stderr,
            )
            raise SystemExit(1)
        retriever = LangchainRetriever(
            project_uuid=args.project,
            chat_model=prompt.model_name,
            temperature=prompt.temperature,
            system_prompt=prompt.system_prompt,
        )
        try:
            if args.question is not None:
                await asyncio.to_thread(_print_langchain_stream, retriever, args.question)
            else:
                await _langchain_repl(retriever, args.project)
        finally:
            retriever.close()
    finally:
        await engine.dispose()


def _print_langchain_stream(retriever: LangchainRetriever, question: str) -> None:
    print(_banner("LANGCHAIN AGENT"))
    for message in retriever.stream(question):
        message.pretty_print()


async def _langchain_repl(retriever: LangchainRetriever, project: UUID) -> None:
    print(f"Interactive LANGCHAIN retrieval - project {project}")
    print("Type a question and press Enter. Ctrl-D or 'quit' to exit.")
    while True:
        try:
            question = (await asyncio.to_thread(input, "\nquestion> ")).strip()
        except EOFError:
            print()
            return
        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            return
        try:
            await asyncio.to_thread(_print_langchain_stream, retriever, question)
        except Exception:
            traceback.print_exc()


async def _run_once(
    service: RetrievalService,
    question: str,
    project: UUID,
    config: RetrievalConfig,
    as_json: bool,
) -> None:
    result = await service.retrieve(question, project, config)
    if as_json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    else:
        _print_trace(result)


async def _repl(
    service: RetrievalService, project: UUID, config: RetrievalConfig, as_json: bool
) -> None:
    print(
        f"Interactive retrieval — project {project}, modality={config.modality.value}, "
        f"multi_query={config.multi_query} bm25={config.use_bm25} "
        f"cross_encoder={config.use_cross_encoder} top_k={config.top_k}"
    )
    print("Type a question and press Enter. Ctrl-D or 'quit' to exit.")
    while True:
        try:
            question = (await asyncio.to_thread(input, "\nquestion> ")).strip()
        except EOFError:
            print()
            return
        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            return
        # Keep the session alive: a bad question (or a transient API error) shouldn't end it.
        try:
            await _run_once(service, question, project, config, as_json)
        except RetrievalError as exc:
            print(f"retrieval error: {exc}", file=sys.stderr)
        except Exception:
            traceback.print_exc()


def _banner(title: str) -> str:
    return f"\n=== {title} " + "=" * max(0, SECTION_WIDTH - len(title) - 5)


def _abbrev(value: UUID) -> str:
    return str(value)[:UUID_ABBREV_LENGTH]


def _truncate(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= PREVIEW_LENGTH:
        return collapsed
    return collapsed[:PREVIEW_LENGTH].rstrip() + "..."


def _print_trace(result: RetrievalResult) -> None:
    cfg = result.config

    print(_banner("SCOPE"))
    print(f"  modality     : {result.scope.modality.value}")
    print(f"  project_uuid : {result.scope.project_uuid}")
    if result.scope.lv_document_uuid is not None:
        print(f"  lv_document  : {result.scope.lv_document_uuid}")
    print(
        f"  config       : multi_query={cfg.multi_query} bm25={cfg.use_bm25} "
        f"cross_encoder={cfg.use_cross_encoder} candidate_k={cfg.candidate_k} top_k={cfg.top_k}"
    )

    print(_banner("QUERIES"))
    for i, query in enumerate(result.queries):
        tag = "original" if query.is_original else f"variant {i}"
        print(f"  [{i}] ({tag}) {query.query_text}")

    print(_banner("PER-QUERY HITS"))
    for i, query in enumerate(result.queries):
        print(f"  q{i}: {query.query_text}")
        print(f"    dense ({len(query.dense_hits)}):")
        for rank, hit in enumerate(query.dense_hits, start=1):
            _print_hit(rank, hit)
        if query.lexical_hits:
            print(f"    lexical ({len(query.lexical_hits)}):")
            for rank, hit in enumerate(query.lexical_hits, start=1):
                _print_hit(rank, hit)

    print(_banner(f"FUSED POOL (rrf_applied={result.rrf_applied}, {len(result.fused)} chunks)"))
    for rank, fused in enumerate(result.fused, start=1):
        contributors = ", ".join(f"{label}#{r}" for label, r in fused.contributing_ranks.items())
        oz = f" OZ {fused.oz}" if fused.oz else ""
        print(
            f"  {rank:>3}. rrf={fused.rrf_score:.5f} [{contributors}] "
            f"doc {_abbrev(fused.source_doc_uuid)}{oz}"
        )
        print(f"       {fused.text_preview}")

    print(_banner("RERANK"))
    if result.rerank_applied:
        for trace in result.reranked:
            print(
                f"  {trace.rank:>3}. relevance={trace.relevance_score:.5f} "
                f"chunk {_abbrev(trace.chunk_uuid)}"
            )
    else:
        print("  cross-encoder: off")

    print(_banner(f"FINAL CONTEXT ({len(result.context)} sources)"))
    for chunk in result.context:
        bits = [chunk.source_doc_type.value]
        if chunk.oz:
            bits.append(f"OZ {chunk.oz}")
        if chunk.stl_nr:
            bits.append(f"STL {chunk.stl_nr}")
        bits.append(f"doc {_abbrev(chunk.source_doc_uuid)}")
        if chunk.source_doc_pages:
            bits.append(f"pages {chunk.source_doc_pages}")
        print(f"  [{chunk.source_number}] ({', '.join(bits)})")
        print(f"      {_truncate(chunk.chunk_text)}")

    print(_banner("ANSWER"))
    print(result.answer)


def _print_hit(rank: int, hit: HitTrace) -> None:
    oz = f" OZ {hit.oz}" if hit.oz else ""
    print(
        f"      {rank:>3}. score={hit.score:.4f} {hit.source_doc_type.value} "
        f"doc {_abbrev(hit.source_doc_uuid)}{oz}"
    )
    print(f"           {hit.text_preview}")


if __name__ == "__main__":
    asyncio.run(main())
