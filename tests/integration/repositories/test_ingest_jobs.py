from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_job_events import ingest_job_events
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository


async def _document(conn: AsyncConnection, file_name: str = "p.pdf") -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-IJ",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name=file_name,
            number_of_pages=1,
        )
    )
    return doc.document_uuid


async def _project_with_document(conn: AsyncConnection, vergabe_id: str) -> tuple[UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id=vergabe_id,
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    return project.project_uuid, doc.document_uuid


async def _add_event(
    conn: AsyncConnection, job_uuid: UUID, event: str, phase: str, ts: datetime
) -> None:
    # Explicit ts: func.now() ties within one transaction, so DISTINCT-ON-latest needs real ordering.
    await conn.execute(
        insert(ingest_job_events).values(
            job_uuid=job_uuid, event=event, pipeline_phase=phase, message=event, ts=ts
        )
    )


async def test_add_defaults_to_queued_and_get(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    doc = await _document(conn)
    created = await repo.add(NewIngestJob(document_uuid=doc))
    assert created.status == IngestStatus.QUEUED
    fetched = await repo.get(created.job_uuid)
    assert fetched is not None
    assert fetched.job_uuid == created.job_uuid
    assert fetched.status == IngestStatus.QUEUED


async def test_set_status(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    doc = await _document(conn)
    created = await repo.add(NewIngestJob(document_uuid=doc))
    updated = await repo.set_status(created.job_uuid, IngestStatus.DONE)
    assert updated is not None
    assert updated.status == IngestStatus.DONE
    assert (await repo.get(created.job_uuid)).status == IngestStatus.DONE


async def test_claim_next_returns_one_then_none(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    doc = await _document(conn)
    queued = await repo.add(NewIngestJob(document_uuid=doc))

    claimed = await repo.claim_next()
    assert claimed is not None
    assert claimed.job_uuid == queued.job_uuid
    assert claimed.status == IngestStatus.RUNNING

    # Nothing left in the queue.
    assert await repo.claim_next() is None


async def test_status_for_project_returns_latest_event_per_job(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    project_uuid, document_uuid = await _project_with_document(conn, "VG-ST1")
    job = await repo.add(NewIngestJob(document_uuid=document_uuid))
    await repo.set_status(job.job_uuid, IngestStatus.RUNNING)
    await _add_event(conn, job.job_uuid, "started", "ingest", datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC))
    await _add_event(conn, job.job_uuid, "thumbnails_generated", "thumbnails", datetime(2026, 6, 3, 12, 0, 5, tzinfo=UTC))

    rows = await repo.status_for_project(project_uuid)
    assert len(rows) == 1  # one row per job, latest event only
    row = rows[0]
    assert row.document_uuid == document_uuid
    assert row.job_uuid == job.job_uuid
    assert row.status == IngestStatus.RUNNING
    assert row.latest_event == "thumbnails_generated"
    assert row.latest_phase == "thumbnails"


async def test_status_for_project_queued_job_has_no_event(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    project_uuid, document_uuid = await _project_with_document(conn, "VG-ST2")
    await repo.add(NewIngestJob(document_uuid=document_uuid))

    rows = await repo.status_for_project(project_uuid)
    assert len(rows) == 1
    assert rows[0].status == IngestStatus.QUEUED
    assert rows[0].latest_event is None
    assert rows[0].latest_ts is None


async def test_status_for_project_scopes_to_the_project(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    project_a, doc_a = await _project_with_document(conn, "VG-ST3A")
    _project_b, doc_b = await _project_with_document(conn, "VG-ST3B")
    await repo.add(NewIngestJob(document_uuid=doc_a))
    await repo.add(NewIngestJob(document_uuid=doc_b))

    rows = await repo.status_for_project(project_a)
    assert [r.document_uuid for r in rows] == [doc_a]
