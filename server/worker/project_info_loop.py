"""Projektinfo consumer: a third competing-consumer loop over the project_info_jobs
queue, running alongside the ingestion and eval loops in the same worker process.

A job is claimable only once its project has no queued or running ingest job, so it
waits for the ZIP's documents to settle. The loop runs `ProjectInfoService`, then marks
the job DONE with the per-query result or FAILED with the error; both writes are fenced
on the lease, mirroring the other loops. A ProjectInfoActivityWriter streams the job's
activity lines and its periodic flush keeps the lease fresh. Idle ticks park poison jobs
and prune old activity rows.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings.client import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search.client import SearchClient
from shared.config import settings
from shared.models.enums import IngestStatus
from shared.services.ingestion.activity import ProjectInfoActivityWriter
from shared.services.ingestion.ingestion_service import (
    FAILURE_MESSAGE_LIMIT,
    UnitOfWorkFactory,
)
from shared.services.project_info import ProjectInfoService
from shared.services.project_info.progress import ProjectInfoPhase
from shared.services.project_info.prompts import load_project_info_prompt
from shared.services.retrieval import RetrievalService

logger = logging.getLogger("worker.project_info")


async def process_one_project_info(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    engine: AsyncEngine,
    llm: LLMClient,
    embeddings: EmbeddingsClient,
    search: SearchClient,
    reranker: RerankClient,
) -> bool:
    """Claim and run one project-info job under this worker's lease. Returns False when
    nothing is claimable. A failure is marked FAILED and swallowed so the polling loop
    survives."""
    async with uow_factory() as uow:
        job = await uow.project_info_jobs.claim_next(
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            max_attempts=settings.worker_max_attempts,
        )
    if job is None:
        return False
    logger.info(
        "[worker] claimed project-info job %s for project %s (attempt %d) as %s",
        job.job_uuid,
        job.project_uuid,
        job.attempts,
        worker_id,
    )

    try:
        async with ProjectInfoActivityWriter(
            uow_factory,
            worker_id=worker_id,
            job_uuid=job.job_uuid,
            project_uuid=job.project_uuid,
        ) as activity:
            started = time.monotonic()
            activity.emit(
                f"claimed (attempt {job.attempts}) by {worker_id}: "
                f"language={job.language} overwrite={job.overwrite}",
                ProjectInfoPhase.CLAIM.value,
            )
            try:
                prompt = None
                if not settings.calculator_mock:
                    async with uow_factory() as uow:
                        prompt = await load_project_info_prompt(uow.conn)
                retrieval = RetrievalService(
                    engine=engine,
                    llm=llm,
                    embeddings=embeddings,
                    search=search,
                    reranker=reranker,
                )
                result = await ProjectInfoService(uow_factory).run(
                    job,
                    retrieval=retrieval,
                    llm=llm,
                    prompt=prompt,
                    activity=activity.emit,
                )
            except Exception as exc:
                activity.emit(
                    f"failed after {time.monotonic() - started:.1f} s: "
                    f"{type(exc).__name__}: {str(exc)[:FAILURE_MESSAGE_LIMIT]}"
                )
                raise
            found = sum(1 for r in result.values() if r.gefunden)
            activity.emit(
                f"done in {time.monotonic() - started:.1f} s, "
                f"{found} of {len(result)} found",
                ProjectInfoPhase.WRITE.value,
            )
        async with uow_factory() as uow:
            done = await uow.project_info_jobs.set_status(
                job.job_uuid,
                IngestStatus.DONE,
                expected_worker=worker_id,
                result=result,
            )
        if done is None:
            logger.warning(
                "[worker] project-info job %s lease lost before DONE; another worker "
                "owns it",
                job.job_uuid,
            )
        else:
            logger.info(
                "[worker] project-info job %s DONE (%d of %d found)",
                job.job_uuid,
                found,
                len(result),
            )
    except Exception as exc:
        logger.exception("[worker] project-info job %s FAILED", job.job_uuid)
        async with uow_factory() as uow:
            await uow.project_info_jobs.set_status(
                job.job_uuid,
                IngestStatus.FAILED,
                expected_worker=worker_id,
                error=str(exc),
            )
    return True


async def project_info_loop(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    engine: AsyncEngine,
    llm: LLMClient,
    embeddings: EmbeddingsClient,
    search: SearchClient,
    reranker: RerankClient,
    shutdown: asyncio.Event,
) -> None:
    """Poll the project_info_jobs queue until shutdown, parking poison jobs and pruning
    old activity while idle."""
    logger.info("[worker] project-info loop started as %s", worker_id)
    while not shutdown.is_set():
        ran = await process_one_project_info(
            uow_factory,
            worker_id=worker_id,
            engine=engine,
            llm=llm,
            embeddings=embeddings,
            search=search,
            reranker=reranker,
        )
        if ran:
            continue
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=settings.activity_retention_hours
        )
        async with uow_factory() as uow:
            parked = await uow.project_info_jobs.park_exhausted(
                lease_seconds=settings.worker_lease_seconds,
                max_attempts=settings.worker_max_attempts,
            )
            pruned = await uow.project_info_activity.delete_older_than(cutoff)
        if parked:
            logger.warning(
                "[worker] parked %d exhausted project-info job(s) as FAILED", parked
            )
        if pruned:
            logger.info("[worker] pruned %d old project-info activity row(s)", pruned)
        try:
            await asyncio.wait_for(
                shutdown.wait(), timeout=settings.worker_poll_interval_seconds
            )
        except TimeoutError:
            pass
