"""Crash-recovery behaviour of IngestJobRepository: lease reclaim, fencing, parking, requeue.

now() is the transaction timestamp, constant within the per-test transaction, so a just-claimed
job's lease never looks stale on its own. Tests backdate locked_at explicitly to simulate a worker
that claimed a job and then died.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingest_jobs import ingest_jobs
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository

_LEASE = 60.0
_PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


async def _queued_job(
    conn: AsyncConnection, vergabe_id: str = "VG-REC"
) -> tuple[UUID, UUID, UUID]:
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
    return project.project_uuid, doc.document_uuid, job.job_uuid


async def _expire_lease(conn: AsyncConnection, job_uuid: UUID) -> None:
    """Backdate a claimed job's lease so it looks expired (now() is constant within the txn)."""
    await conn.execute(
        update(ingest_jobs).where(ingest_jobs.c.job_uuid == job_uuid).values(locked_at=_PAST)
    )


async def test_claim_sets_lease_and_first_attempt(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    claimed = await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)
    assert claimed is not None
    assert claimed.job_uuid == job_uuid
    assert claimed.status == IngestStatus.RUNNING
    assert claimed.locked_by == "w1"
    assert claimed.locked_at is not None
    assert claimed.attempts == 1


async def test_expired_running_job_is_reclaimed_and_attempts_increment(
    conn: AsyncConnection,
) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)
    await _expire_lease(conn, job_uuid)  # w1 "died" mid-job

    reclaimed = await repo.claim_next(worker_id="w2", lease_seconds=_LEASE, max_attempts=3)
    assert reclaimed is not None
    assert reclaimed.job_uuid == job_uuid
    assert reclaimed.locked_by == "w2"
    assert reclaimed.attempts == 2


async def test_fresh_running_job_is_not_reclaimed(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)
    # The lease is fresh (locked_at == now), so there is nothing claimable.
    assert await repo.claim_next(worker_id="w2", lease_seconds=_LEASE, max_attempts=3) is None


async def test_exhausted_job_is_not_reclaimed(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=1)  # attempts -> 1
    await _expire_lease(conn, job_uuid)
    # attempts (1) is not < max (1): no more retries.
    assert await repo.claim_next(worker_id="w2", lease_seconds=_LEASE, max_attempts=1) is None


async def test_set_status_is_fenced_on_lease_owner(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)

    # A worker that no longer owns the lease cannot write the terminal status.
    lost = await repo.set_status(job_uuid, IngestStatus.DONE, expected_worker="someone-else")
    assert lost is None
    refreshed = await repo.get(job_uuid)
    assert refreshed is not None and refreshed.status == IngestStatus.RUNNING

    # The lease owner can, and the lease is cleared on terminal.
    done = await repo.set_status(job_uuid, IngestStatus.DONE, expected_worker="w1")
    assert done is not None
    assert done.status == IngestStatus.DONE
    assert done.locked_at is None


async def test_park_exhausted_marks_failed(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=1)  # attempts -> 1
    await _expire_lease(conn, job_uuid)

    parked = await repo.park_exhausted(lease_seconds=_LEASE, max_attempts=1)
    assert parked == 1
    refreshed = await repo.get(job_uuid)
    assert refreshed is not None and refreshed.status == IngestStatus.FAILED


async def test_park_exhausted_spares_a_retryable_job(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)  # attempts -> 1
    await _expire_lease(conn, job_uuid)
    # Expired, but attempts (1) < max (3): keep it for retry, don't park.
    assert await repo.park_exhausted(lease_seconds=_LEASE, max_attempts=3) == 0
    refreshed = await repo.get(job_uuid)
    assert refreshed is not None and refreshed.status == IngestStatus.RUNNING


async def test_requeue_resets_in_place(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, _d, job_uuid = await _queued_job(conn)
    await repo.claim_next(worker_id="w1", lease_seconds=_LEASE, max_attempts=3)
    await repo.set_status(job_uuid, IngestStatus.FAILED, expected_worker="w1")

    requeued = await repo.requeue(job_uuid)
    assert requeued is not None
    assert requeued.status == IngestStatus.QUEUED
    assert requeued.attempts == 0
    assert requeued.locked_by is None
    assert requeued.locked_at is None


async def test_latest_for_document(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    _p, doc_uuid, job_uuid = await _queued_job(conn, vergabe_id="VG-LFD")
    found = await repo.latest_for_document(doc_uuid)
    assert found is not None and found.job_uuid == job_uuid
    assert await repo.latest_for_document(uuid4()) is None


async def test_list_for_console_filters_by_project_and_status(conn: AsyncConnection) -> None:
    repo = IngestJobRepository(conn)
    proj_a, _da, job_a = await _queued_job(conn, vergabe_id="VG-LC-A")
    _pb, _db, job_b = await _queued_job(conn, vergabe_id="VG-LC-B")

    a_jobs = await repo.list_for_console(project_uuid=proj_a)
    assert [j.job_uuid for j in a_jobs] == [job_a]

    await repo.set_status(job_b, IngestStatus.FAILED)
    failed = await repo.list_for_console(status=IngestStatus.FAILED)
    assert [j.job_uuid for j in failed] == [job_b]
