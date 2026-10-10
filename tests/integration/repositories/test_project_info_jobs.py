"""ProjectInfoJobRepository: the claim waits for the project's ingest jobs to settle, plus
the lease mechanics shared with the ingest queue.

now() is the transaction timestamp, constant within the per-test transaction, so tests backdate
locked_at explicitly to simulate a worker that claimed a job and then died.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.project_info_jobs import project_info_jobs
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus, ProjectInfoQuery
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.models.project_info_job import NewProjectInfoJob, ProjectInfoResult
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository

_LEASE = 60.0
_PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


async def _project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    return project.project_uuid


async def _ingest_job(conn: AsyncConnection, project_uuid: UUID, status: IngestStatus) -> UUID:
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
    return job.job_uuid


async def _info_job(conn: AsyncConnection, project_uuid: UUID) -> UUID:
    job = await ProjectInfoJobRepository(conn).add(
        NewProjectInfoJob(project_uuid=project_uuid, language="de", overwrite=True)
    )
    return job.job_uuid


async def _claim(repo: ProjectInfoJobRepository, worker: str = "w1", max_attempts: int = 3):
    return await repo.claim_next(worker_id=worker, lease_seconds=_LEASE, max_attempts=max_attempts)


async def test_not_claimable_while_ingest_job_queued(conn: AsyncConnection) -> None:
    project = await _project(conn)
    await _ingest_job(conn, project, IngestStatus.QUEUED)
    await _info_job(conn, project)
    assert await _claim(ProjectInfoJobRepository(conn)) is None


async def test_not_claimable_while_ingest_job_running(conn: AsyncConnection) -> None:
    project = await _project(conn)
    await _ingest_job(conn, project, IngestStatus.RUNNING)
    await _info_job(conn, project)
    assert await _claim(ProjectInfoJobRepository(conn)) is None


async def test_claimable_once_ingest_job_done(conn: AsyncConnection) -> None:
    project = await _project(conn)
    ingest = await _ingest_job(conn, project, IngestStatus.QUEUED)
    info = await _info_job(conn, project)
    repo = ProjectInfoJobRepository(conn)
    assert await _claim(repo) is None

    await IngestJobRepository(conn).set_status(ingest, IngestStatus.DONE)
    claimed = await _claim(repo)

    assert claimed is not None
    assert claimed.job_uuid == info
    assert claimed.status == IngestStatus.RUNNING
    assert claimed.locked_by == "w1"
    assert claimed.attempts == 1


async def test_failed_ingest_job_does_not_block(conn: AsyncConnection) -> None:
    project = await _project(conn)
    await _ingest_job(conn, project, IngestStatus.DONE)
    await _ingest_job(conn, project, IngestStatus.FAILED)
    info = await _info_job(conn, project)
    claimed = await _claim(ProjectInfoJobRepository(conn))
    assert claimed is not None and claimed.job_uuid == info


async def test_other_projects_open_ingest_jobs_do_not_block(conn: AsyncConnection) -> None:
    busy = await _project(conn)
    await _ingest_job(conn, busy, IngestStatus.QUEUED)
    await _info_job(conn, busy)
    idle = await _project(conn)
    idle_info = await _info_job(conn, idle)

    claimed = await _claim(ProjectInfoJobRepository(conn))

    assert claimed is not None and claimed.job_uuid == idle_info


async def test_expired_lease_is_reclaimed_until_attempts_spent(conn: AsyncConnection) -> None:
    project = await _project(conn)
    info = await _info_job(conn, project)
    repo = ProjectInfoJobRepository(conn)
    await _claim(repo, "w1", max_attempts=2)
    assert await _claim(repo, "w2", max_attempts=2) is None  # lease still fresh

    await conn.execute(
        update(project_info_jobs).where(project_info_jobs.c.job_uuid == info).values(locked_at=_PAST)
    )
    reclaimed = await _claim(repo, "w2", max_attempts=2)
    assert reclaimed is not None
    assert reclaimed.locked_by == "w2"
    assert reclaimed.attempts == 2

    await conn.execute(
        update(project_info_jobs).where(project_info_jobs.c.job_uuid == info).values(locked_at=_PAST)
    )
    assert await _claim(repo, "w3", max_attempts=2) is None
    assert await repo.park_exhausted(lease_seconds=_LEASE, max_attempts=2) == 1
    parked = await repo.get(info)
    assert parked is not None and parked.status == IngestStatus.FAILED


async def test_set_status_is_fenced_and_stores_result(conn: AsyncConnection) -> None:
    project = await _project(conn)
    info = await _info_job(conn, project)
    repo = ProjectInfoJobRepository(conn)
    await _claim(repo)
    result = {
        ProjectInfoQuery.PROJECT_VERGABENUMMER: ProjectInfoResult(
            gefunden=True, wert="VG-1", konfidenz=0.9, beleg="Vergabenummer VG-1", query_version=2
        )
    }

    assert await repo.set_status(info, IngestStatus.DONE, expected_worker="other", result=result) is None

    done = await repo.set_status(info, IngestStatus.DONE, expected_worker="w1", result=result)
    assert done is not None
    assert done.status == IngestStatus.DONE
    assert done.locked_at is None
    assert done.result == result


async def test_open_job_and_latest_for_project(conn: AsyncConnection) -> None:
    project = await _project(conn)
    repo = ProjectInfoJobRepository(conn)
    assert await repo.open_job(project) is None
    assert await repo.latest_for_project(project) is None

    info = await _info_job(conn, project)
    open_job = await repo.open_job(project)
    assert open_job is not None and open_job.job_uuid == info

    await _claim(repo)
    assert await repo.open_job(project) is not None  # running is still open

    await repo.set_status(info, IngestStatus.FAILED, expected_worker="w1", error="boom")
    assert await repo.open_job(project) is None
    latest = await repo.latest_for_project(project)
    assert latest is not None and latest.error == "boom"


async def test_touch_lease_keeps_job_from_being_reclaimed(conn: AsyncConnection) -> None:
    project = await _project(conn)
    info = await _info_job(conn, project)
    repo = ProjectInfoJobRepository(conn)
    await _claim(repo)
    await conn.execute(
        update(project_info_jobs).where(project_info_jobs.c.job_uuid == info).values(locked_at=_PAST)
    )

    await repo.touch_lease(info, "someone-else")  # not the owner: no effect
    assert (await repo.get(info)).locked_at == _PAST  # type: ignore[union-attr]
    await repo.touch_lease(info, "w1")

    assert await _claim(repo, "w2") is None
