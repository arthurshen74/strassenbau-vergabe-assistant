from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.ingest_job import NewIngestJob
from shared.domain.ingest_job_event import IngestEventType, NewIngestJobEvent
from shared.domain.project import NewProject
from shared.domain.project_document import NewProjectDocument
from shared.domain.project_document_type import NewProjectDocumentType
from shared.repositories.ingest_job_events import IngestJobEventRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.project_document_types import ProjectDocumentTypeRepository
from shared.repositories.project_documents import ProjectDocumentRepository
from shared.repositories.projects import ProjectRepository


async def _make_job(conn: AsyncConnection) -> tuple[UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-2026-0042",
            project_name="Autobahn A1 Brückensanierung",
            vergabestelle="Autobahn GmbH des Bundes",
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
    job = await IngestJobRepository(conn).add(
        NewIngestJob(
            project_uuid=project.project_uuid,
            project_document_uuid=document.project_document_uuid,
        )
    )
    return project.project_uuid, job.ingest_job_uuid


async def test_add_and_list_for_job(conn: AsyncConnection) -> None:
    _, job_uuid = await _make_job(conn)
    repo = IngestJobEventRepository(conn)

    await repo.add(
        NewIngestJobEvent(ingest_job_uuid=job_uuid, event=IngestEventType.STARTED)
    )
    await repo.add(
        NewIngestJobEvent(
            ingest_job_uuid=job_uuid,
            event=IngestEventType.PROGRESS,
            phase="extract",
            message="parsing pages",
        )
    )

    events = await repo.list_for_job(job_uuid)
    assert len(events) == 2
    assert {e.event for e in events} == {
        IngestEventType.STARTED,
        IngestEventType.PROGRESS,
    }


async def test_deleting_project_cascades_to_events(conn: AsyncConnection) -> None:
    project_uuid, job_uuid = await _make_job(conn)
    repo = IngestJobEventRepository(conn)
    await repo.add(
        NewIngestJobEvent(ingest_job_uuid=job_uuid, event=IngestEventType.STARTED)
    )

    await ProjectRepository(conn).delete(project_uuid)

    assert await repo.list_for_job(job_uuid) == []
