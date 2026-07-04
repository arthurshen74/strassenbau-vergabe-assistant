"""Eval-run endpoints: enqueue a run (the worker's eval loop picks it up via the eval_runs
queue) and read runs, their live progress events, and per-item results. Not project-prefixed:
a run's scope is optional (chat_values runs project-free); list filters by project instead.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import Principal, get_connection, get_current_user, get_uow
from shared.db.unit_of_work import UnitOfWork
from shared.models.eval_run import EvalResult, EvalRun, EvalRunCreate, EvalRunEvent
from shared.services.eval.run_service import EvalRunService

router = APIRouter(prefix="/eval-runs", tags=["eval-runs"])


@router.post("", response_model=EvalRun, status_code=status.HTTP_201_CREATED)
async def enqueue_eval_run(
    payload: EvalRunCreate,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(get_current_user),
) -> EvalRun:
    try:
        return await EvalRunService(uow.conn).enqueue(payload, user_id=principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("", response_model=list[EvalRun])
async def list_eval_runs(
    project_uuid: UUID | None = None,
    limit: int = 50,
    conn: AsyncConnection = Depends(get_connection),
) -> list[EvalRun]:
    return await EvalRunService(conn).list_runs(project_uuid=project_uuid, limit=limit)


async def _get_run(conn: AsyncConnection, eval_run_uuid: UUID) -> EvalRun:
    run = await EvalRunService(conn).get_run(eval_run_uuid)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="eval run not found")
    return run


@router.get("/{eval_run_uuid}", response_model=EvalRun)
async def get_eval_run(
    eval_run_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> EvalRun:
    return await _get_run(conn, eval_run_uuid)


@router.get("/{eval_run_uuid}/events", response_model=list[EvalRunEvent])
async def list_eval_run_events(
    eval_run_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[EvalRunEvent]:
    await _get_run(conn, eval_run_uuid)
    return await EvalRunService(conn).events(eval_run_uuid)


@router.get("/{eval_run_uuid}/results", response_model=list[EvalResult])
async def list_eval_run_results(
    eval_run_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[EvalResult]:
    await _get_run(conn, eval_run_uuid)
    return await EvalRunService(conn).results(eval_run_uuid)
