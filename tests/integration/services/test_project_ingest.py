from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository
from shared.services.project_service import ProjectService


def _service(conn: AsyncConnection) -> ProjectService:
    return ProjectService(
        ProjectRepository(conn), DocumentRepository(conn), IngestJobRepository(conn)
    )


async def _project_and_document(conn: AsyncConnection, vergabe_id: str):
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


async def test_enqueue_ingest_creates_a_queued_job(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _project_and_document(conn, "VG-EN1")

    job = await _service(conn).enqueue_ingest(project_uuid, document_uuid)

    assert job is not None
    assert job.document_uuid == document_uuid
    assert job.status == IngestStatus.QUEUED
    # The new job shows up in the project's status snapshot the SSE stream reads.
    rows = await IngestJobRepository(conn).status_for_project(project_uuid)
    assert [r.job_uuid for r in rows] == [job.job_uuid]


async def test_enqueue_ingest_requeues_existing_job_in_place(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _project_and_document(conn, "VG-EN4")
    repo = IngestJobRepository(conn)
    first = await _service(conn).enqueue_ingest(project_uuid, document_uuid)
    assert first is not None
    # Simulate the job having run and failed with a retry spent.
    await repo.claim_next(worker_id="w1", lease_seconds=60.0, max_attempts=3)  # attempts -> 1
    await repo.set_status(first.job_uuid, IngestStatus.FAILED, expected_worker="w1")

    # Reingest requeues the SAME job in place (no new row), with a reset retry budget.
    again = await _service(conn).enqueue_ingest(project_uuid, document_uuid)
    assert again is not None
    assert again.job_uuid == first.job_uuid
    assert again.status == IngestStatus.QUEUED
    assert again.attempts == 0
    rows = await repo.status_for_project(project_uuid)
    assert [r.job_uuid for r in rows] == [first.job_uuid]  # still exactly one job


async def test_enqueue_ingest_missing_document_returns_none(conn: AsyncConnection) -> None:
    project_uuid, _ = await _project_and_document(conn, "VG-EN2")
    assert await _service(conn).enqueue_ingest(project_uuid, uuid4()) is None


async def test_enqueue_ingest_foreign_document_returns_none(conn: AsyncConnection) -> None:
    _project_a, doc_a = await _project_and_document(conn, "VG-EN3A")
    project_b, _doc_b = await _project_and_document(conn, "VG-EN3B")
    # doc_a belongs to project A, so enqueuing it under project B is rejected.
    assert await _service(conn).enqueue_ingest(project_b, doc_a) is None
