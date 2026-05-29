from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.ingest_job import IngestStatus, NewIngestJob
from shared.domain.project import NewProject
from shared.domain.project_document import NewProjectDocument
from shared.domain.project_document_type import NewProjectDocumentType
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.project_document_types import ProjectDocumentTypeRepository
from shared.repositories.project_documents import ProjectDocumentRepository
from shared.repositories.projects import ProjectRepository


async def _make_document(conn: AsyncConnection) -> tuple[UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-2026-0042",
            project_name="Autobahn A1 Brückensanierung",
            vergabe_stelle="Autobahn GmbH des Bundes",
            project_location="Niedersachsen",
        )
    )
    doc_type = await ProjectDocumentTypeRepository(conn).add(
        NewProjectDocumentType(document_type="LV")
    )
    document = await ProjectDocumentRepository(conn).add(
        NewProjectDocument(
            project_uuid=project.project_uuid,
            document_filename="LV_001.pdf",
            document_type_uuid=doc_type.document_type_uuid,
            number_of_pages=12,
        )
    )
    return project.project_uuid, document.project_document_uuid


async def test_add_defaults_to_queued_and_get_round_trips(
    conn: AsyncConnection,
) -> None:
    project_uuid, document_uuid = await _make_document(conn)
    repo = IngestJobRepository(conn)

    created = await repo.add(
        NewIngestJob(project_uuid=project_uuid, project_document_uuid=document_uuid)
    )

    assert created.status == IngestStatus.QUEUED
    fetched = await repo.get(created.ingest_job_uuid)
    assert fetched is not None
    assert fetched.ingest_job_uuid == created.ingest_job_uuid
    assert fetched.project_document_uuid == document_uuid


async def test_set_status_transitions(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _make_document(conn)
    repo = IngestJobRepository(conn)
    job = await repo.add(
        NewIngestJob(project_uuid=project_uuid, project_document_uuid=document_uuid)
    )

    updated = await repo.set_status(job.ingest_job_uuid, IngestStatus.DONE)

    assert updated is not None
    assert updated.status == IngestStatus.DONE


async def test_claim_next_marks_running_then_returns_none(
    conn: AsyncConnection,
) -> None:
    project_uuid, document_uuid = await _make_document(conn)
    repo = IngestJobRepository(conn)
    await repo.add(
        NewIngestJob(project_uuid=project_uuid, project_document_uuid=document_uuid)
    )

    claimed = await repo.claim_next()
    assert claimed is not None
    assert claimed.status == IngestStatus.RUNNING

    assert await repo.claim_next() is None


async def test_deleting_project_cascades_to_jobs(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _make_document(conn)
    repo = IngestJobRepository(conn)
    job = await repo.add(
        NewIngestJob(project_uuid=project_uuid, project_document_uuid=document_uuid)
    )

    await ProjectRepository(conn).delete(project_uuid)

    assert await repo.get(job.ingest_job_uuid) is None
