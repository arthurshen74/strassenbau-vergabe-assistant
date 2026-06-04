from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.ingest_job import NewIngestJob
from shared.models.ingest_job_event import NewIngestJobEvent
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_job_events import IngestJobEventRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository


async def _job(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-IJE",
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
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=doc.document_uuid))
    return job.job_uuid


async def test_add_and_list_for_job(conn: AsyncConnection) -> None:
    repo = IngestJobEventRepository(conn)
    job_uuid = await _job(conn)
    await repo.add(
        NewIngestJobEvent(
            job_uuid=job_uuid,
            event="started",
            pipeline_phase="parse",
            message="parsing began",
        )
    )
    await repo.add(
        NewIngestJobEvent(
            job_uuid=job_uuid,
            event="progress",
            message="halfway",
        )
    )
    listed = await repo.list_for_job(job_uuid)
    assert len(listed) == 2
    assert {e.event for e in listed} == {"started", "progress"}
    assert all(e.job_uuid == job_uuid for e in listed)
    started = next(e for e in listed if e.event == "started")
    assert started.pipeline_phase == "parse"


async def test_list_for_job_empty(conn: AsyncConnection) -> None:
    repo = IngestJobEventRepository(conn)
    job_uuid = await _job(conn)
    assert await repo.list_for_job(job_uuid) == []


async def test_latest_event_ts_returns_most_recent_match(conn: AsyncConnection) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-IJE-LE",
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
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=doc.document_uuid))
    repo = IngestJobEventRepository(conn)

    assert await repo.latest_event_ts(doc.document_uuid, "completed") is None
    await repo.add(NewIngestJobEvent(job_uuid=job.job_uuid, event="started", message="x"))
    await repo.add(NewIngestJobEvent(job_uuid=job.job_uuid, event="completed", message="done"))
    assert await repo.latest_event_ts(doc.document_uuid, "completed") is not None
