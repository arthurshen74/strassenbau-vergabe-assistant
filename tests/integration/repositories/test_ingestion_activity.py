"""IngestionActivityLogRepository: append, cursor tail (id-ordered, job-scoped), and prune."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingestion_activity_log_archive import ingestion_activity_log_archive
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.ingest_job import NewIngestJob
from shared.models.ingestion_activity import NewIngestionActivity
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.repositories.projects import ProjectRepository


async def _job_and_doc(conn: AsyncConnection, vergabe_id: str = "VG-ACT") -> tuple[UUID, UUID]:
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
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=doc.document_uuid))
    return job.job_uuid, doc.document_uuid


def _line(job_uuid: UUID, doc_uuid: UUID, message: str) -> NewIngestionActivity:
    return NewIngestionActivity(
        job_uuid=job_uuid,
        document_uuid=doc_uuid,
        worker_id="w1",
        phase="chunk",
        message=message,
    )


async def test_add_many_and_tail_orders_by_id(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_uuid, doc_uuid = await _job_and_doc(conn)
    await repo.add_many([_line(job_uuid, doc_uuid, f"m{i}") for i in range(3)])

    rows = await repo.tail(job_uuid, after_id=0, limit=10)
    assert [r.message for r in rows] == ["m0", "m1", "m2"]
    assert rows[0].id < rows[1].id < rows[2].id
    assert rows[0].worker_id == "w1"


async def test_tail_after_cursor_returns_only_newer(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_uuid, doc_uuid = await _job_and_doc(conn)
    await repo.add_many([_line(job_uuid, doc_uuid, f"m{i}") for i in range(3)])

    first_page = await repo.tail(job_uuid, after_id=0, limit=2)
    assert len(first_page) == 2
    rest = await repo.tail(job_uuid, after_id=first_page[-1].id, limit=10)
    assert [r.message for r in rest] == ["m2"]


async def test_tail_scopes_to_one_job(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_a, doc_a = await _job_and_doc(conn, vergabe_id="VG-ACT-A")
    job_b, doc_b = await _job_and_doc(conn, vergabe_id="VG-ACT-B")
    await repo.add_many([_line(job_a, doc_a, "a")])
    await repo.add_many([_line(job_b, doc_b, "b")])

    rows = await repo.tail(job_a, after_id=0, limit=10)
    assert [r.message for r in rows] == ["a"]


async def test_archive_stale_moves_old_rows_preserving_id(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_uuid, doc_uuid = await _job_and_doc(conn)
    await repo.add_many([_line(job_uuid, doc_uuid, "recent")])
    [active] = await repo.tail(job_uuid, after_id=0, limit=10)

    # Cutoff in the future moves the just-written row into the archive (ts defaults to now()).
    moved = await repo.archive_stale(datetime.now(timezone.utc) + timedelta(days=1))
    assert moved == 1
    assert await repo.tail(job_uuid, after_id=0, limit=10) == []  # gone from the active table

    archived = (
        await conn.execute(
            select(ingestion_activity_log_archive).where(
                ingestion_activity_log_archive.c.job_uuid == job_uuid
            )
        )
    ).mappings().all()
    assert len(archived) == 1
    assert archived[0]["id"] == active.id  # original id preserved
    assert archived[0]["message"] == "recent"


async def test_list_for_document_unions_active_and_archive(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_uuid, doc_uuid = await _job_and_doc(conn)
    await repo.add_many([_line(job_uuid, doc_uuid, "first")])
    # Move "first" into the archive, then add "second" to the active table.
    assert await repo.archive_stale(datetime.now(timezone.utc) + timedelta(days=1)) == 1
    await repo.add_many([_line(job_uuid, doc_uuid, "second")])

    rows = await repo.list_for_document(doc_uuid)
    assert [r.message for r in rows] == ["first", "second"]  # archive then active, by id


async def test_archive_stale_keeps_recent_rows(conn: AsyncConnection) -> None:
    repo = IngestionActivityLogRepository(conn)
    job_uuid, doc_uuid = await _job_and_doc(conn)
    await repo.add_many([_line(job_uuid, doc_uuid, "recent")])

    # Cutoff in the past moves nothing.
    moved = await repo.archive_stale(datetime.now(timezone.utc) - timedelta(days=1))
    assert moved == 0
    assert len(await repo.tail(job_uuid, after_id=0, limit=10)) == 1
