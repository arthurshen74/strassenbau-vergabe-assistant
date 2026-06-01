"""Sinks that receive a ``UsageEvent`` from an OpenRouter client.

``LoggingUsageSink`` emits one structured log line and is the default sink (works offline and in
tests). ``DatabaseUsageSink`` persists each event to Postgres in its OWN short transaction, owning
an ``AsyncEngine`` and bypassing any caller ``UnitOfWork``: the cost was really incurred at
OpenRouter, so it must survive a business-transaction rollback.

Sinks do not swallow their own errors; failure isolation is the calling client's single
responsibility (it wraps parse + emit so usage recording never fails the primary call).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.openrouter.usage.parser import UsageEvent
from shared.models.openrouter_usage import NewOpenRouterUsage
from shared.repositories.openrouter_usage import OpenRouterUsageRepository

logger = logging.getLogger(__name__)


@runtime_checkable
class UsageSink(Protocol):
    async def emit(self, event: UsageEvent) -> None: ...


class LoggingUsageSink:
    """Records a usage event as a single structured log line."""

    def __init__(self, logger_: logging.Logger | None = None) -> None:
        self._logger = logger_ or logger

    async def emit(self, event: UsageEvent) -> None:
        self._logger.info(
            "openrouter usage: %s model=%s tokens=%s cost=%s",
            event.operation,
            event.model,
            event.total_tokens,
            event.cost,
            extra={"openrouter_usage": event.model_dump(mode="json")},
        )


class DatabaseUsageSink:
    """Persists a usage event to Postgres in its own short transaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def emit(self, event: UsageEvent) -> None:
        new = NewOpenRouterUsage.model_validate(event.model_dump())
        async with self._engine.begin() as conn:
            await OpenRouterUsageRepository(conn).add(new)
