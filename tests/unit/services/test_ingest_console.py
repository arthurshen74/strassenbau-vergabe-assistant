from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models.console_job import ConsoleJobRow
from shared.models.enums import ConsoleJobKind, IngestStatus
from shared.models.ingest_schema import ConsoleJobRead
from shared.services.ingest_admin import diff_console_jobs

_T0 = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)


def _row(kind: ConsoleJobKind = ConsoleJobKind.INGEST, **fields: object) -> ConsoleJobRow:
    base: dict[str, object] = {
        "kind": kind,
        "job_uuid": uuid4(),
        "project_uuid": uuid4(),
        "project_name": "tender",
        "status": IngestStatus.QUEUED,
        "attempts": 0,
        "created_at": _T0,
        "updated_at": _T0,
    }
    if kind is ConsoleJobKind.INGEST:
        base |= {"document_uuid": uuid4(), "file_name": "a.pdf"}
    return ConsoleJobRow(**{**base, **fields})


def test_first_tick_always_emits_even_empty() -> None:
    event, fingerprint = diff_console_jobs(None, [])
    assert event == {"event": "console_jobs", "data": {"event": "console_jobs", "jobs": []}}
    assert fingerprint == ()


def test_unchanged_list_emits_nothing() -> None:
    rows = [_row(), _row(ConsoleJobKind.PROJECT_INFO)]
    _event, fingerprint = diff_console_jobs(None, rows)
    event, again = diff_console_jobs(fingerprint, rows)
    assert event is None
    assert again == fingerprint


def test_status_change_emits_snapshot() -> None:
    row = _row()
    _e, fingerprint = diff_console_jobs(None, [row])
    running = row.model_copy(update={"status": IngestStatus.RUNNING, "locked_by": "w1"})
    event, _f = diff_console_jobs(fingerprint, [running])
    assert event is not None
    assert [j["status"] for j in event["data"]["jobs"]] == ["running"]


def test_new_activity_line_emits_snapshot() -> None:
    row = _row(status=IngestStatus.RUNNING, latest_ts=_T0)
    _e, fingerprint = diff_console_jobs(None, [row])
    moved = row.model_copy(
        update={"latest_ts": _T0 + timedelta(seconds=1), "latest_message": "next"}
    )
    event, _f = diff_console_jobs(fingerprint, [moved])
    assert event is not None
    assert event["data"]["jobs"][0]["latest_message"] == "next"


def test_new_row_emits_snapshot() -> None:
    first = _row()
    _e, fingerprint = diff_console_jobs(None, [first])
    event, _f = diff_console_jobs(fingerprint, [_row(ConsoleJobKind.PROJECT_INFO), first])
    assert event is not None
    assert [j["kind"] for j in event["data"]["jobs"]] == ["project_info", "ingest"]


def test_console_job_read_validates_both_kinds() -> None:
    ingest = ConsoleJobRead.model_validate(_row(latest_phase="chunk", latest_message="m", latest_ts=_T0))
    assert ingest.kind is ConsoleJobKind.INGEST
    assert ingest.file_name == "a.pdf"

    info = ConsoleJobRead.model_validate(_row(ConsoleJobKind.PROJECT_INFO))
    assert info.kind is ConsoleJobKind.PROJECT_INFO
    assert info.document_uuid is None and info.file_name is None
    assert info.latest_phase is None


def test_console_job_read_rejects_unknown_kind() -> None:
    payload = _row().model_dump() | {"kind": "eval"}
    with pytest.raises(ValidationError):
        ConsoleJobRead.model_validate(payload)
