"""RAG reference questions: project-scoped CRUD for the retrieval/answer gold set.

Refs are validated against the project's ingested documents on every write; questions without
refs are flagged refs_missing on read (they count only toward answer grading).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import Principal, get_connection, get_current_user, get_uow
from shared.db.unit_of_work import UnitOfWork
from shared.models.rag_ground_truth import RagGroundTruthRead, RagGroundTruthUpsert
from shared.repositories.projects import ProjectRepository
from shared.services.rag_ground_truth import RagGroundTruthService

router = APIRouter(prefix="/projects", tags=["rag-ground-truth"])


async def _ensure_project(conn: AsyncConnection, project_uuid: UUID) -> None:
    if await ProjectRepository(conn).get(project_uuid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")


@router.get("/{project_uuid}/rag-ground-truth", response_model=list[RagGroundTruthRead])
async def list_rag_ground_truth(
    project_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[RagGroundTruthRead]:
    await _ensure_project(conn, project_uuid)
    return await RagGroundTruthService(conn).list(project_uuid)


@router.post(
    "/{project_uuid}/rag-ground-truth",
    response_model=RagGroundTruthRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_rag_ground_truth(
    project_uuid: UUID,
    payload: RagGroundTruthUpsert,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(get_current_user),
) -> RagGroundTruthRead:
    await _ensure_project(uow.conn, project_uuid)
    try:
        return await RagGroundTruthService(uow.conn).create(
            project_uuid=project_uuid, payload=payload, user_id=principal.user_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.put(
    "/{project_uuid}/rag-ground-truth/{rag_ground_truth_uuid}",
    response_model=RagGroundTruthRead,
)
async def update_rag_ground_truth(
    project_uuid: UUID,
    rag_ground_truth_uuid: UUID,
    payload: RagGroundTruthUpsert,
    uow: UnitOfWork = Depends(get_uow),
    _principal: Principal = Depends(get_current_user),
) -> RagGroundTruthRead:
    await _ensure_project(uow.conn, project_uuid)
    try:
        return await RagGroundTruthService(uow.conn).update(
            project_uuid=project_uuid,
            rag_ground_truth_uuid=rag_ground_truth_uuid,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/{project_uuid}/rag-ground-truth/{rag_ground_truth_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rag_ground_truth(
    project_uuid: UUID,
    rag_ground_truth_uuid: UUID,
    uow: UnitOfWork = Depends(get_uow),
    _principal: Principal = Depends(get_current_user),
) -> None:
    await _ensure_project(uow.conn, project_uuid)
    if not await RagGroundTruthService(uow.conn).delete(project_uuid, rag_ground_truth_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG reference question not found",
        )
