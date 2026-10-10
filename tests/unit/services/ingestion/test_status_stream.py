from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from shared.models.enums import IngestStatus
from shared.models.ingest_job import IngestJobStatusRow
from shared.services.ingestion.status_stream import diff_status

_T0 = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)


def _row(
    *,
    document_uuid: UUID,
    job_uuid: UUID,
    status: IngestStatus,
    event: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    ts: datetime | None = None,
) -> IngestJobStatusRow:
    return IngestJobStatusRow(
        document_uuid=document_uuid,
        job_uuid=job_uuid,
        status=status,
        latest_event=event,
        latest_phase=phase,
        latest_message=message,
        latest_ts=ts,
    )


def test_lifecycle_transitions_emit_the_right_events() -> None:
    doc, job = uuid4(), uuid4()
    state: dict[UUID, tuple] = {}

    events, state = diff_status(state, [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.QUEUED)])
    assert [e["event"] for e in events] == ["ingest_queued"]

    events, state = diff_status(
        state,
        [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.RUNNING, event="started", phase="ingest", message="f.pdf", ts=_T0)],
    )
    assert [e["event"] for e in events] == ["ingest_started"]

    events, state = diff_status(
        state,
        [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.RUNNING, event="thumbnails_generated", phase="thumbnails", message="2 thumbnails", ts=datetime(2026, 6, 3, 12, 0, 1, tzinfo=UTC))],
    )
    assert events[0]["event"] == "ingest_progress"
    assert events[0]["data"]["phase"] == "thumbnails"
    assert events[0]["data"]["message"] == "2 thumbnails"

    events, state = diff_status(
        state,
        [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.DONE, event="completed", phase="ingest", message="done", ts=datetime(2026, 6, 3, 12, 0, 2, tzinfo=UTC))],
    )
    assert [e["event"] for e in events] == ["ingest_completed"]


def test_unchanged_view_emits_nothing() -> None:
    doc, job = uuid4(), uuid4()
    row = _row(document_uuid=doc, job_uuid=job, status=IngestStatus.RUNNING, event="started", phase="ingest", message="f", ts=_T0)
    events, state = diff_status({}, [row])
    assert len(events) == 1
    events, _ = diff_status(state, [row])
    assert events == []


def test_failed_with_failure_event_carries_phase_and_message() -> None:
    doc, job = uuid4(), uuid4()
    events, _ = diff_status(
        {},
        [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.FAILED, event="failed", phase="chunk", message="boom", ts=_T0)],
    )
    assert events[0]["event"] == "ingest_error"
    assert events[0]["data"]["phase"] == "chunk"
    assert events[0]["data"]["message"] == "boom"


def test_failed_without_failure_event_falls_back_to_generic_reason() -> None:
    doc, job = uuid4(), uuid4()
    # Latest event is a success event (e.g. crash before the failure event was written).
    events, _ = diff_status(
        {},
        [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.FAILED, event="document_chunks_indexed", phase="chunk", message="5 chunks", ts=_T0)],
    )
    assert events[0]["event"] == "ingest_error"
    assert events[0]["data"]["phase"] is None
    assert events[0]["data"]["message"] == "ingestion failed"


def test_every_event_carries_document_uuid() -> None:
    doc = uuid4()
    rows = [
        _row(document_uuid=doc, job_uuid=uuid4(), status=IngestStatus.QUEUED),
        _row(document_uuid=doc, job_uuid=uuid4(), status=IngestStatus.RUNNING, event="started", phase="ingest", message="f", ts=_T0),
        _row(document_uuid=doc, job_uuid=uuid4(), status=IngestStatus.DONE, event="completed", phase="ingest", message="d", ts=_T0),
        _row(document_uuid=doc, job_uuid=uuid4(), status=IngestStatus.FAILED, event="failed", phase="lv", message="x", ts=_T0),
    ]
    events, _ = diff_status({}, rows)
    assert len(events) == 4
    assert all(e["data"]["document_uuid"] == str(doc) for e in events)


def test_only_changed_jobs_emit() -> None:
    doc_a, job_a = uuid4(), uuid4()
    doc_b, job_b = uuid4(), uuid4()
    rows = [
        _row(document_uuid=doc_a, job_uuid=job_a, status=IngestStatus.QUEUED),
        _row(document_uuid=doc_b, job_uuid=job_b, status=IngestStatus.QUEUED),
    ]
    _, state = diff_status({}, rows)

    # job_a advances to running; job_b unchanged.
    rows[0] = _row(document_uuid=doc_a, job_uuid=job_a, status=IngestStatus.RUNNING, event="started", phase="ingest", message="f", ts=_T0)
    events, _ = diff_status(state, rows)
    assert len(events) == 1
    assert events[0]["data"]["job_uuid"] == str(job_a)


def test_skipped_job_emits_ingest_skipped() -> None:
    doc, job = uuid4(), uuid4()

    events, _ = diff_status(
        {}, [_row(document_uuid=doc, job_uuid=job, status=IngestStatus.SKIPPED)]
    )

    assert [e["event"] for e in events] == ["ingest_skipped"]
    assert events[0]["data"]["document_uuid"] == str(doc)
