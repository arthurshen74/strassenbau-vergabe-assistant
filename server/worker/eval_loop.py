"""Eval-run consumer: a second competing-consumer loop over the eval_runs queue, running
alongside the ingestion loop in the same worker process. Claims a run, dispatches to the
shared runner for its kind, streams progress into eval_run_events (each event also
refreshes the lease, which is the heartbeat), and finalizes DONE with summary + per-item
results, or FAILED with the error. Terminal writes are fenced on the lease, mirroring
the ingest loop.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.embeddings.client import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search.client import SearchClient
from shared.config import settings
from shared.models.enums import EvalRunKind, EvalRunStatus
from shared.models.eval_run import EvalRun
from shared.services.eval.calculator_runner import run_calculator_gold
from shared.services.eval.chat_runner import (
    DEFAULT_CHAT_DATASET,
    resolve_dataset,
    run_chat_values,
)
from shared.services.eval.grade import metrics_to_dict, position_to_dict
from shared.services.eval.grade_chat import chat_fixture_to_dict, chat_metrics_to_dict
from shared.services.ingestion.ingestion_service import UnitOfWorkFactory

logger = logging.getLogger("worker.eval")


async def _execute(
    run: EvalRun,
    *,
    engine: AsyncEngine,
    llm: LLMClient,
    embeddings: EmbeddingsClient,
    search: SearchClient,
    reranker: RerankClient,
    emit,
) -> tuple[dict, dict, list[tuple[str, dict]]]:
    """Dispatch to the runner for the run's kind; returns (summary, prompt_versions,
    rows)."""
    params = run.params or {}
    if run.kind == EvalRunKind.CALCULATOR_GOLD:
        assert run.project_uuid is not None  # enforced at enqueue
        result = await run_calculator_gold(
            engine=engine,
            llm=llm,
            embeddings=embeddings,
            search=search,
            reranker=reranker,
            project_uuid=run.project_uuid,
            abs_tol=str(params.get("abs_tol", "0")),
            limit=params.get("limit"),
            emit=emit,
        )
        summary = {
            "metrics": metrics_to_dict(result.metrics),
            "positions": len(result.results),
            "skipped": result.skipped,
        }
        rows = [(r.id, position_to_dict(r)) for r in result.results]
        return summary, result.prompt_versions, rows
    if run.kind == EvalRunKind.CHAT_VALUES:
        dataset = resolve_dataset(str(params.get("dataset", DEFAULT_CHAT_DATASET)))
        result = await run_chat_values(
            engine=engine,
            llm=llm,
            dataset=dataset,
            abs_tol=str(params.get("abs_tol", "0")),
            emit=emit,
        )
        summary = {
            "metrics": chat_metrics_to_dict(result.metrics),
            "fixtures": len(result.results),
            "dataset": str(dataset),
        }
        rows = [(r.id, chat_fixture_to_dict(r)) for r in result.results]
        return summary, {"ekt_chat_values": result.prompt_version}, rows
    raise RuntimeError(f"eval kind {run.kind.value!r} not yet supported by this worker")


async def process_one_eval(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    engine: AsyncEngine,
    llm: LLMClient,
    embeddings: EmbeddingsClient,
    search: SearchClient,
    reranker: RerankClient,
) -> bool:
    """Claim and execute one eval run under this worker's lease. Returns False when
    nothing is claimable. A failure is marked FAILED and swallowed so the polling loop
    survives."""
    async with uow_factory() as uow:
        run = await uow.eval_runs.claim_next(
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            max_attempts=settings.worker_max_attempts,
        )
    if run is None:
        return False
    logger.info(
        "[worker] claimed eval run %s (%s, attempt %d) as %s",
        run.eval_run_uuid,
        run.kind.value,
        run.attempts,
        worker_id,
    )

    async def emit(message: str, *, run_uuid: UUID = run.eval_run_uuid) -> None:
        # Each event commits immediately (own transaction) so the UI's poll sees live
        # progress; the lease touch doubles as the heartbeat during long runs.
        async with uow_factory() as uow:
            await uow.eval_run_events.add(run_uuid, message)
            await uow.eval_runs.touch_lease(run_uuid, worker_id)

    try:
        await emit(f"claimed (attempt {run.attempts}) by {worker_id}")
        summary, prompt_versions, rows = await _execute(
            run,
            engine=engine,
            llm=llm,
            embeddings=embeddings,
            search=search,
            reranker=reranker,
            emit=emit,
        )
        async with uow_factory() as uow:
            await uow.eval_results.add_many(run.eval_run_uuid, rows)
            done = await uow.eval_runs.finalize(
                run.eval_run_uuid,
                status=EvalRunStatus.DONE,
                expected_worker=worker_id,
                summary=summary,
                prompt_versions=prompt_versions,
            )
        if done is None:
            logger.warning(
                "[worker] eval run %s lease lost before DONE; another worker owns it",
                run.eval_run_uuid,
            )
        else:
            logger.info(
                "[worker] eval run %s DONE (%d result rows)",
                run.eval_run_uuid,
                len(rows),
            )
    except Exception as exc:
        logger.exception("[worker] eval run %s FAILED", run.eval_run_uuid)
        async with uow_factory() as uow:
            await uow.eval_run_events.add(run.eval_run_uuid, f"FAILED: {exc}")
            await uow.eval_runs.finalize(
                run.eval_run_uuid,
                status=EvalRunStatus.FAILED,
                expected_worker=worker_id,
                error=str(exc),
            )
    return True


async def eval_loop(
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
    """Poll the eval_runs queue until shutdown, parking poison runs while idle."""
    logger.info("[worker] eval loop started as %s", worker_id)
    while not shutdown.is_set():
        ran = await process_one_eval(
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
        async with uow_factory() as uow:
            parked = await uow.eval_runs.park_exhausted(
                lease_seconds=settings.worker_lease_seconds,
                max_attempts=settings.worker_max_attempts,
            )
        if parked:
            logger.warning("[worker] parked %d exhausted eval run(s) as FAILED", parked)
        try:
            await asyncio.wait_for(
                shutdown.wait(), timeout=settings.worker_poll_interval_seconds
            )
        except asyncio.TimeoutError:
            pass
