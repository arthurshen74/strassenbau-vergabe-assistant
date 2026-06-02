from __future__ import annotations

import logging
from typing import Any

import pytest

from shared.services.ingestion.progress import (
    IngestEvent,
    IngestPhase,
    log_progress,
    record_event,
)


def test_log_progress_emits_event_and_message_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="shared.services.ingestion.progress"):
        log_progress(
            event=IngestEvent.COMPLETED, phase=IngestPhase.INGEST, message="all done"
        )

    [record] = caplog.records
    assert record.levelno == logging.INFO
    text = record.getMessage()
    assert "completed" in text and "ingest" in text and "all done" in text


class _RaisingEvents:
    async def add(self, *_a: Any, **_k: Any) -> None:
        raise AssertionError("record_event must not write when jobless")


async def test_record_event_is_noop_when_jobless() -> None:
    # Passing a None job_uuid must not touch the repository.
    await record_event(
        _RaisingEvents(),  # type: ignore[arg-type]
        None,
        event=IngestEvent.STARTED,
        phase=IngestPhase.INGEST,
        message="x",
    )
