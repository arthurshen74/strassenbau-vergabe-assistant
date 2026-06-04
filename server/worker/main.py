"""Ingestion worker: a competing-consumer loop over the ingest_jobs queue.

The process builds the long-lived clients once, then polls
`IngestJobRepository.claim_next()` (SELECT ... FOR UPDATE SKIP LOCKED) for the oldest queued job,
runs the full ingestion pipeline for it, and marks it DONE or FAILED. Several worker containers can
run this loop concurrently: the SKIP LOCKED claim hands each a distinct job, so Postgres is the
allocator -- there is no central dispatcher. When the queue is empty the loop sleeps
`settings.worker_poll_interval_seconds` before re-checking, waking immediately on SIGTERM/SIGINT so a
clean stop lets the in-flight job finish first.

    python -m worker.main

Crash recovery: each claimed job holds a lease (locked_by + locked_at). An ActivityWriter refreshes
locked_at while the job runs, so a worker killed mid-job lets its lease expire and another worker
reclaims the job on a later poll (claim_next), retrying up to settings.worker_max_attempts before it
is parked FAILED. Idle ticks run park_exhausted and prune old activity rows.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from datetime import datetime, timedelta, timezone
from functools import partial

from shared.clients.embeddings.client import EmbeddingsClient
from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_telemetry_sinks,
)
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient, build_storage_client
from shared.config import settings
from shared.db.engine import make_engine
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import IngestStatus
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.ingestion import IngestionService
from shared.services.ingestion.activity import ActivityWriter
from shared.services.ingestion.ingestion_service import UnitOfWorkFactory
from shared.services.ingestion.langchain_pipeline import LangchainIngestor
from shared.services.ingestion.progress import IngestPhase
from shared.services.prompt_runner import PromptRunner

logger = logging.getLogger("worker.main")


async def process_one(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    storage: StorageClient,
    search: SearchClient,
    embeddings: EmbeddingsClient,
    prompts: PromptRunner,
    langchain_ingestor: LangchainIngestor,
) -> bool:
    """Claim and run one queued (or reclaimable) job under this worker's lease. Returns False when
    nothing is claimable.

    The claim runs in its own transaction so the QUEUED/expired -> RUNNING transition commits and
    the SKIP LOCKED row lock releases before the long ingest begins. An ActivityWriter streams
    granular progress and keeps the lease fresh during the run; terminal status writes are fenced on
    the lease (expected_worker), so a worker whose job was reclaimed mid-run cannot clobber the new
    owner. A failure is marked FAILED and the exception is swallowed so the polling loop survives."""
    async with uow_factory() as uow:
        job = await uow.ingest_jobs.claim_next(
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            max_attempts=settings.worker_max_attempts,
        )
    if job is None:
        return False
    logger.info(
        "[worker] claimed job %s for document %s (attempt %d) as %s",
        job.job_uuid,
        job.document_uuid,
        job.attempts,
        worker_id,
    )

    try:
        async with ActivityWriter(
            uow_factory,
            worker_id=worker_id,
            job_uuid=job.job_uuid,
            document_uuid=job.document_uuid,
        ) as activity:
            activity.emit(
                f"claimed (attempt {job.attempts}) by {worker_id}", IngestPhase.INGEST.value
            )
            service = IngestionService(
                uow_factory,
                storage,
                search,
                embeddings,
                prompts,
                langchain_ingestor,
                activity=activity.emit,
            )
            result = await service.ingest_document(job.document_uuid, job_uuid=job.job_uuid)
        async with uow_factory() as uow:
            done = await uow.ingest_jobs.set_status(
                job.job_uuid, IngestStatus.DONE, expected_worker=worker_id
            )
        if done is None:
            logger.warning(
                "[worker] job %s lease lost before DONE; another worker now owns it", job.job_uuid
            )
            return True
        logger.info(
            "[worker] job %s DONE: %d source lines, %d thumbnails, %d langchain chunks, "
            "%d document chunks, %d LV items, %d LV chunks",
            job.job_uuid,
            result.source_lines,
            result.thumbnails,
            result.langchain_chunks,
            result.document_chunks,
            result.lv_items,
            result.lv_chunks,
        )
    except Exception:
        logger.exception("[worker] job %s FAILED", job.job_uuid)
        async with uow_factory() as uow:
            await uow.ingest_jobs.set_status(
                job.job_uuid, IngestStatus.FAILED, expected_worker=worker_id
            )
    return True


async def run_maintenance(uow_factory: UnitOfWorkFactory) -> None:
    """Idle-time upkeep: park poison jobs (expired RUNNING past the retry cap) as FAILED so they
    surface to the console, and archive activity rows older than the retention window (moved to the
    cold table, not deleted, so a document's full history survives)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.activity_retention_hours)
    async with uow_factory() as uow:
        parked = await uow.ingest_jobs.park_exhausted(
            lease_seconds=settings.worker_lease_seconds,
            max_attempts=settings.worker_max_attempts,
        )
        archived = await uow.ingestion_activity.archive_stale(cutoff)
    if parked:
        logger.warning("[worker] parked %d exhausted job(s) as FAILED", parked)
    if archived:
        logger.info("[worker] archived %d old activity row(s)", archived)


async def run_worker() -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    engine = make_engine(settings.database_url, pool_size=5, application_name="worker")
    storage = build_storage_client()
    search = SearchClient.from_settings()
    sinks = build_telemetry_sinks(engine)
    embeddings = build_embeddings_client(sinks, engine)
    llm = build_llm_client(sinks)
    langchain_ingestor = LangchainIngestor(embeddings)

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    try:
        await search.ensure_index()
        uow_factory = partial(unit_of_work, engine)
        logger.info(
            "[worker] started as %s; polling every %ss",
            worker_id,
            settings.worker_poll_interval_seconds,
        )
        # One prompt connection for the process: the PromptRunner reads the seeded LV prompt; the
        # service's uow_factory opens separate transactional connections per stage and per job.
        async with engine.connect() as prompt_conn:
            prompts = PromptRunner(PromptVersionRepository(prompt_conn), llm)
            while not shutdown.is_set():
                ran = await process_one(
                    uow_factory,
                    worker_id=worker_id,
                    storage=storage,
                    search=search,
                    embeddings=embeddings,
                    prompts=prompts,
                    langchain_ingestor=langchain_ingestor,
                )
                if ran:
                    continue
                # Idle: park poison jobs and prune old activity, then wait (waking on shutdown).
                await run_maintenance(uow_factory)
                try:
                    await asyncio.wait_for(
                        shutdown.wait(), timeout=settings.worker_poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
        logger.info("[worker] shutdown signal received; exiting")
    finally:
        langchain_ingestor.close()
        await llm.aclose()
        await search.close()
        await embeddings.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
