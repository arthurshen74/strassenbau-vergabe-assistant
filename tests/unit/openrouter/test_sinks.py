from __future__ import annotations

import logging
from decimal import Decimal

from shared.clients.openrouter.usage import LoggingUsageSink, UsageEvent
from shared.models.enums import UsageOperation


def _event() -> UsageEvent:
    return UsageEvent(
        operation=UsageOperation.EMBEDDING,
        model="openai/text-embedding-3-small",
        prompt_tokens=8,
        total_tokens=8,
        cost=Decimal("0.0000004"),
    )


async def test_logging_sink_emits_one_record(caplog) -> None:
    sink = LoggingUsageSink()
    with caplog.at_level(logging.INFO, logger="shared.clients.openrouter.usage.sinks"):
        await sink.emit(_event())

    records = [r for r in caplog.records if "openrouter usage" in r.getMessage()]
    assert len(records) == 1
    assert records[0].openrouter_usage["model"] == "openai/text-embedding-3-small"


async def test_logging_sink_is_runtime_checkable() -> None:
    from shared.clients.openrouter.usage import UsageSink

    assert isinstance(LoggingUsageSink(), UsageSink)
