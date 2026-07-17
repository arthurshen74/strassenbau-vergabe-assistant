"""Builds the OpenRouter clients wired to persist telemetry to Postgres.

One `AsyncEngine` yields one `TelemetrySinks` (a `DatabaseUsageSink` plus a
`DatabaseExecutionLogSink`), shared across every client built from it: the same usage
sink for the LLM, embeddings, and rerank clients, and the same execution-log sink for
the LLM client. This is the single construction point for the API and the scripts, so
they all record usage and execution logs the same way instead of each re-deriving (and
forgetting) the sink wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings import (
    EmbeddingsClient,
    NullEmbeddingCache,
    PostgresEmbeddingCache,
)
from shared.clients.embeddings.cache import EmbeddingCache
from shared.clients.llm.client import LLMClient
from shared.clients.llm.execution_log_sinks import (
    CompositeExecutionLogSink,
    DatabaseExecutionLogSink,
)
from shared.clients.llm.otel_sink import OTelExecutionLogSink
from shared.clients.openrouter.usage import DatabaseUsageSink
from shared.clients.rerank import RerankClient
from shared.config import settings


@dataclass(frozen=True)
class TelemetrySinks:
    """The DB-backed sinks for one engine, shared across the clients built from it."""

    usage: DatabaseUsageSink
    execution_log: DatabaseExecutionLogSink


def build_telemetry_sinks(engine: AsyncEngine) -> TelemetrySinks:
    return TelemetrySinks(
        usage=DatabaseUsageSink(engine),
        execution_log=DatabaseExecutionLogSink(engine),
    )


def build_llm_client(sinks: TelemetrySinks) -> LLMClient:
    # The LLMClient powers dispatch + the calculator's in-node model calls; tee its
    # execution log to Postgres AND Phoenix (OpenInference LLM spans). Project chat's
    # ChatOpenAI is traced by the LangChain auto-instrumentor instead, so its drained
    # events stay on the DB sink (sinks.execution_log).
    execution_log = CompositeExecutionLogSink(
        [sinks.execution_log, OTelExecutionLogSink()]
    )
    return LLMClient(usage_sink=sinks.usage, execution_log_sink=execution_log)


def build_embedding_cache(engine: AsyncEngine) -> EmbeddingCache:
    if not settings.embedding_cache_enabled:
        return NullEmbeddingCache()
    return PostgresEmbeddingCache(engine)


def build_embeddings_client(
    sinks: TelemetrySinks, engine: AsyncEngine
) -> EmbeddingsClient:
    return EmbeddingsClient(usage_sink=sinks.usage, cache=build_embedding_cache(engine))


def build_rerank_client(sinks: TelemetrySinks) -> RerankClient:
    return RerankClient(usage_sink=sinks.usage)
