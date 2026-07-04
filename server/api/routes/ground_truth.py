"""Eval curation endpoints: browse/edit/delete calculation gold, read Gate-B corrections.

Gold rows are listed with their staleness against the current recipe worklist, upserted (which
also serves the "Gold neu bestätigen" re-stamp), and deleted. Corrections are read-only — they
are only ever written by the Gate B capture flow (shared.services.ground_truth); here they feed
the error-analysis view (filtered list + variable-by-reason summary).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import Principal, get_connection, get_current_user, get_uow
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import VariableCorrectionReason
from shared.models.ground_truth import (
    CorrectionSummaryRow,
    GroundTruthRead,
    GroundTruthUpsert,
    VariableCorrection,
)
from shared.repositories.projects import ProjectRepository
from shared.services.ground_truth import GroundTruthService

router = APIRouter(prefix="/projects", tags=["ground-truth"])


async def _ensure_project(conn: AsyncConnection, project_uuid: UUID) -> None:
    if await ProjectRepository(conn).get(project_uuid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")


@router.get("/{project_uuid}/ground-truth", response_model=list[GroundTruthRead])
async def list_ground_truth(
    project_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[GroundTruthRead]:
    await _ensure_project(conn, project_uuid)
    return await GroundTruthService(conn).list_gold(project_uuid)


@router.put("/{project_uuid}/ground-truth/{lv_item_uuid}", response_model=GroundTruthRead)
async def upsert_ground_truth(
    project_uuid: UUID,
    lv_item_uuid: UUID,
    payload: GroundTruthUpsert,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(get_current_user),
) -> GroundTruthRead:
    await _ensure_project(uow.conn, project_uuid)
    try:
        return await GroundTruthService(uow.conn).upsert_gold(
            project_uuid=project_uuid,
            lv_item_uuid=lv_item_uuid,
            payload=payload,
            user_id=principal.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/{project_uuid}/ground-truth/{lv_item_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ground_truth(
    project_uuid: UUID,
    lv_item_uuid: UUID,
    uow: UnitOfWork = Depends(get_uow),
    _principal: Principal = Depends(get_current_user),
) -> None:
    await _ensure_project(uow.conn, project_uuid)
    if not await GroundTruthService(uow.conn).delete_gold(project_uuid, lv_item_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ground truth not found"
        )


@router.get("/{project_uuid}/corrections", response_model=list[VariableCorrection])
async def list_corrections(
    project_uuid: UUID,
    variable_name: str | None = None,
    reason: VariableCorrectionReason | None = None,
    conn: AsyncConnection = Depends(get_connection),
) -> list[VariableCorrection]:
    await _ensure_project(conn, project_uuid)
    return await GroundTruthService(conn).list_corrections(
        project_uuid, variable_name=variable_name, reason=reason
    )


@router.get(
    "/{project_uuid}/corrections/summary", response_model=list[CorrectionSummaryRow]
)
async def corrections_summary(
    project_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[CorrectionSummaryRow]:
    await _ensure_project(conn, project_uuid)
    return await GroundTruthService(conn).corrections_summary(project_uuid)
