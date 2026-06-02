"""Ingestion worker: a competing-consumer loop over the ingest_jobs queue.

The process builds the long-lived clients once, then polls
`IngestJobRepository.claim_next()` (SELECT ... FOR UPDATE SKIP LOCKED) for the oldest queued job,
runs the full ingestion pipeline for it, and marks it DONE or FAILED. Several worker containers can
run this loop concurrently: the SKIP LOCKED claim hands each a distinct job, so Postgres is the
allocator -- there is no central dispatcher. When the queue is empty the loop sleeps
`settings.worker_poll_interval_seconds` before re-checking, waking immediately on SIGTERM/SIGINT so a
clean stop lets the in-flight job finish first.

    python -m worker.main

Known limitation: a worker killed mid-job leaves its row stuck RUNNING (the queue has no
lease/heartbeat); recovering such jobs is future work.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from functools import partial

from shared.clients.embeddings.client import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient, build_storage_client
from shared.config import settings
from shared.db.engine import make_engine
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import IngestStatus
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.ingestion import IngestionService
from shared.services.ingestion.ingestion_service import UnitOfWorkFactory
from shared.services.ingestion.langchain_pipeline import LangchainIngestor
from shared.services.prompt_runner import PromptRunner

logger = logging.getLogger("worker.main")


async def process_one(
    uow_factory: UnitOfWorkFactory,
    *,
    storage: StorageClient,
    search: SearchClient,
    embeddings: EmbeddingsClient,
    prompts: PromptRunner,
    langchain_ingestor: LangchainIngestor,
) -> bool:
    """Claim and run one queued job. Returns False when the queue is empty.

    The claim runs in its own transaction so the QUEUED -> RUNNING transition commits and the SKIP
    LOCKED row lock releases before the long ingest begins. A failed job is marked FAILED and the
    exception is swallowed so the polling loop survives."""
    async with uow_factory() as uow:
        job = await uow.ingest_jobs.claim_next()
    if job is None:
        return False
    logger.info("[worker] claimed job %s for document %s", job.job_uuid, job.document_uuid)

    try:
        service = IngestionService(
            uow_factory, storage, search, embeddings, prompts, langchain_ingestor
        )
        result = await service.ingest_document(job.document_uuid, job_uuid=job.job_uuid)
        async with uow_factory() as uow:
            await uow.ingest_jobs.set_status(job.job_uuid, IngestStatus.DONE)
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
            await uow.ingest_jobs.set_status(job.job_uuid, IngestStatus.FAILED)
    return True


async def run_worker() -> None:
    engine = make_engine(settings.database_url, pool_size=5, application_name="worker")
    storage = build_storage_client()
    search = SearchClient.from_settings()
    embeddings = EmbeddingsClient()
    llm = LLMClient()
    langchain_ingestor = LangchainIngestor(embeddings)

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    try:
        await search.ensure_index()
        uow_factory = partial(unit_of_work, engine)
        logger.info(
            "[worker] started; polling every %ss", settings.worker_poll_interval_seconds
        )
        # One prompt connection for the process: the PromptRunner reads the seeded LV prompt; the
        # service's uow_factory opens separate transactional connections per stage and per job.
        async with engine.connect() as prompt_conn:
            prompts = PromptRunner(PromptVersionRepository(prompt_conn), llm)
            while not shutdown.is_set():
                ran = await process_one(
                    uow_factory,
                    storage=storage,
                    search=search,
                    embeddings=embeddings,
                    prompts=prompts,
                    langchain_ingestor=langchain_ingestor,
                )
                if ran:
                    continue
                # Idle: wait the poll interval, but wake immediately on a shutdown signal.
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
