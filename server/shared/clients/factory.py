"""Builds the OpenRouter clients wired to persist telemetry to Postgres.

One `AsyncEngine` yields one `TelemetrySinks` (a `DatabaseUsageSink` plus a `DatabaseExecutionLogSink`),
shared across every client built from it: the same usage sink for the LLM, embeddings, and rerank
clients, and the same execution-log sink for the LLM client. This is the single construction point
for the API and the scripts, so they all record usage and execution logs the same way instead of
each re-deriving (and forgetting) the sink wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.llm.execution_log_sinks import DatabaseExecutionLogSink
from shared.clients.openrouter.usage import DatabaseUsageSink
from shared.clients.rerank import RerankClient


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
    return LLMClient(usage_sink=sinks.usage, execution_log_sink=sinks.execution_log)


def build_embeddings_client(sinks: TelemetrySinks) -> EmbeddingsClient:
    return EmbeddingsClient(usage_sink=sinks.usage)


def build_rerank_client(sinks: TelemetrySinks) -> RerankClient:
    return RerankClient(usage_sink=sinks.usage)
