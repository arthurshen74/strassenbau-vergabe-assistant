"""Sinks that receive an ``ExecutionLogEvent`` from the LLM client.

``LoggingExecutionLogSink`` emits one structured log line and is the default (works
offline and in tests). ``DatabaseExecutionLogSink`` persists each event to Postgres in
its OWN short transaction, owning an ``AsyncEngine`` and bypassing any caller
``UnitOfWork`` -- mirrors ``DatabaseUsageSink``. Sinks do not swallow their own errors;
failure isolation is the calling client's responsibility.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.models.prompt_execution_log import NewPromptExecutionLog
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository

logger = logging.getLogger(__name__)


@runtime_checkable
class ExecutionLogSink(Protocol):
    async def emit(self, event: ExecutionLogEvent) -> None: ...


class LoggingExecutionLogSink:
    """Records an execution-log event as a single structured log line."""

    def __init__(self, logger_: logging.Logger | None = None) -> None:
        self._logger = logger_ or logger

    async def emit(self, event: ExecutionLogEvent) -> None:
        self._logger.info(
            "llm execution: model=%s prompt=%s/%s finish=%s success=%s latency=%sms",
            event.model,
            event.prompt_type,
            event.prompt_version,
            event.finish_reason,
            event.success,
            event.latency_ms,
            extra={"prompt_execution_log": event.model_dump(mode="json")},
        )


class DatabaseExecutionLogSink:
    """Persists an execution-log event to Postgres in its own short transaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def emit(self, event: ExecutionLogEvent) -> None:
        new = NewPromptExecutionLog.model_validate(event.model_dump())
        async with self._engine.begin() as conn:
            await PromptExecutionLogRepository(conn).add(new)


class CompositeExecutionLogSink:
    """Tees one event to several sinks. Unlike the single sinks above, it isolates each
    sink's failure (logs and continues) so one sink erroring -- e.g. the OTLP exporter
    being down -- never starves the others of the event."""

    def __init__(self, sinks: Sequence[ExecutionLogSink]) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: ExecutionLogEvent) -> None:
        for sink in self._sinks:
            try:
                await sink.emit(event)
            except Exception:
                logger.exception("execution-log sink %s failed", type(sink).__name__)
