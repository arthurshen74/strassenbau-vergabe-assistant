"""Console listing of ingest and Projektinfo jobs: latest activity line per job and the
"active" window (open jobs plus jobs updated within `recent_minutes`).

now() is the transaction timestamp, constant within the per-test transaction, so tests
backdate updated_at relative to it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.project_info_jobs import project_info_jobs
from shared.models.document import NewDocument
from shared.models.enums import ConsoleJobKind, DocumentType, IngestStatus
from shared.models.ingest_job import NewIngestJob
from shared.models.ingestion_activity import NewIngestionActivity
from shared.models.project import NewProject
from shared.models.project_info_activity import NewProjectInfoActivity
from shared.models.project_info_job import NewProjectInfoJob
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.repositories.project_info_activity import ProjectInfoActivityLogRepository
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository


async def _project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(NewProject(project_name="Console"))
    return project.project_uuid


async def _ingest_job(
    conn: AsyncConnection, project_uuid: UUID, status: IngestStatus = IngestStatus.QUEUED
) -> tuple[UUID, UUID]:
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    job = await IngestJobRepository(conn).add(
        NewIngestJob(document_uuid=doc.document_uuid, status=status)
    )
    return doc.document_uuid, job.job_uuid


async def _age(conn: AsyncConnection, table, job_uuid: UUID, minutes: int) -> None:
    await conn.execute(
        update(table)
        .where(table.c.job_uuid == job_uuid)
        .values(updated_at=text(f"now() - interval '{minutes} minutes'"))
    )


async def test_ingest_rows_carry_latest_activity_line(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    doc_uuid, job_uuid = await _ingest_job(conn, project_uuid, IngestStatus.RUNNING)
    _d2, quiet_job = await _ingest_job(conn, project_uuid)
    await IngestionActivityLogRepository(conn).add_many(
        [
            NewIngestionActivity(
                job_uuid=job_uuid, document_uuid=doc_uuid, worker_id="w", phase=phase, message=msg
            )
            for phase, msg in [("ingest", "start"), ("thumbnails", "rendering 3 pages")]
        ]
    )

    rows = await IngestJobRepository(conn).list_for_console(project_uuid=project_uuid)

    by_job = {r.job_uuid: r for r in rows}
    assert by_job[job_uuid].kind is ConsoleJobKind.INGEST
    assert by_job[job_uuid].file_name == "p.pdf"
    assert by_job[job_uuid].project_uuid == project_uuid
    assert (by_job[job_uuid].latest_phase, by_job[job_uuid].latest_message) == (
        "thumbnails",
        "rendering 3 pages",
    )
    assert by_job[job_uuid].latest_ts is not None
    assert by_job[quiet_job].latest_message is None


async def test_ingest_recent_minutes_window(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    _d1, recent = await _ingest_job(conn, project_uuid, IngestStatus.DONE)
    _d2, stale = await _ingest_job(conn, project_uuid, IngestStatus.DONE)
    _d3, queued = await _ingest_job(conn, project_uuid)
    await _age(conn, ingest_jobs, recent, 5)
    await _age(conn, ingest_jobs, stale, 30)
    await _age(conn, ingest_jobs, queued, 30)

    repo = IngestJobRepository(conn)
    active = await repo.list_for_console(project_uuid=project_uuid, recent_minutes=15)
    assert {r.job_uuid for r in active} == {recent, queued}
    everything = await repo.list_for_console(project_uuid=project_uuid)
    assert {r.job_uuid for r in everything} == {recent, stale, queued}


async def test_skipped_job_is_not_active(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    _d1, skipped = await _ingest_job(conn, project_uuid, IngestStatus.SKIPPED)

    repo = IngestJobRepository(conn)
    assert await repo.list_for_console(project_uuid=project_uuid, recent_minutes=15) == []
    listed = await repo.list_for_console(
        project_uuid=project_uuid, statuses=[IngestStatus.SKIPPED]
    )
    assert [r.job_uuid for r in listed] == [skipped]


async def test_project_info_rows_and_window(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    repo = ProjectInfoJobRepository(conn)
    recent = await repo.add(NewProjectInfoJob(project_uuid=project_uuid, language="de"))
    stale = await repo.add(NewProjectInfoJob(project_uuid=project_uuid, language="de"))
    await conn.execute(
        update(project_info_jobs)
        .where(project_info_jobs.c.job_uuid.in_([recent.job_uuid, stale.job_uuid]))
        .values(status=IngestStatus.DONE)
    )
    await _age(conn, project_info_jobs, recent.job_uuid, 5)
    await _age(conn, project_info_jobs, stale.job_uuid, 30)
    await ProjectInfoActivityLogRepository(conn).add_many(
        [
            NewProjectInfoActivity(
                job_uuid=recent.job_uuid,
                project_uuid=project_uuid,
                worker_id="w",
                phase=phase,
                message=msg,
            )
            for phase, msg in [("claim", "claimed"), ("write", "nothing to write")]
        ]
    )

    active = await repo.list_for_console(project_uuid=project_uuid, recent_minutes=15)

    assert [r.job_uuid for r in active] == [recent.job_uuid]
    row = active[0]
    assert row.kind is ConsoleJobKind.PROJECT_INFO
    assert row.document_uuid is None and row.file_name is None
    assert row.project_name == "Console"
    assert (row.latest_phase, row.latest_message) == ("write", "nothing to write")
    everything = await repo.list_for_console(project_uuid=project_uuid)
    assert {r.job_uuid for r in everything} == {recent.job_uuid, stale.job_uuid}


async def test_project_info_requeue_resets_job(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    repo = ProjectInfoJobRepository(conn)
    job = await repo.add(NewProjectInfoJob(project_uuid=project_uuid, language="de"))
    claimed = await repo.claim_next(worker_id="w", lease_seconds=60, max_attempts=3)
    assert claimed is not None and claimed.job_uuid == job.job_uuid
    await repo.set_status(job.job_uuid, IngestStatus.FAILED, expected_worker="w", error="boom")

    requeued = await repo.requeue(job.job_uuid)

    assert requeued is not None
    assert requeued.status is IngestStatus.QUEUED
    assert (requeued.locked_by, requeued.locked_at, requeued.attempts, requeued.error) == (
        None,
        None,
        0,
        None,
    )


async def test_project_info_activity_tail_and_prune(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    job = await ProjectInfoJobRepository(conn).add(
        NewProjectInfoJob(project_uuid=project_uuid, language="de")
    )
    activity = ProjectInfoActivityLogRepository(conn)
    await activity.add_many(
        [
            NewProjectInfoActivity(
                job_uuid=job.job_uuid, project_uuid=project_uuid, worker_id="w", message=m
            )
            for m in ["a", "b", "c"]
        ]
    )
    lines = await activity.tail(job.job_uuid, 0, 10)
    assert [line.message for line in lines] == ["a", "b", "c"]
    assert [line.message for line in await activity.tail(job.job_uuid, lines[0].id, 10)] == [
        "b",
        "c",
    ]

    cutoff = (await conn.execute(text("SELECT now() + interval '1 second'"))).scalar_one()
    assert await activity.delete_older_than(cutoff) == 3
    assert await activity.tail(job.job_uuid, 0, 10) == []
