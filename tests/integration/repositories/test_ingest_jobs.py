from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

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
