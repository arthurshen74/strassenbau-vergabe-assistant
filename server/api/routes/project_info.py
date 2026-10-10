"""Projektinfo endpoints: the project's latest project-info job and a re-run request.

The worker runs the job once the project's ingest jobs have settled; the UI polls GET
until the job is done.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from shared.db.unit_of_work import UnitOfWork
from shared.models.project_info_schema import ProjectInfoJobRead, ProjectInfoRunRequest
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository
from shared.services.project_info.job_service import ProjectInfoJobService

router = APIRouter(prefix="/projects", tags=["project-info"])


def get_project_info_job_service(
    conn: AsyncConnection = Depends(get_connection),
) -> ProjectInfoJobService:
    return ProjectInfoJobService(
        ProjectRepository(conn), ProjectInfoJobRepository(conn)
    )


def get_writable_project_info_job_service(
    uow: UnitOfWork = Depends(get_uow),
) -> ProjectInfoJobService:
    return ProjectInfoJobService(uow.projects, uow.project_info_jobs)


@router.get("/{project_uuid}/project-info", response_model=ProjectInfoJobRead)
async def get_project_info(
    project_uuid: UUID,
    service: ProjectInfoJobService = Depends(get_project_info_job_service),
) -> ProjectInfoJobRead:
    """The project's most recent project-info job."""
    job = await service.latest(project_uuid)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no project-info job"
        )
    return ProjectInfoJobRead.model_validate(job)


@router.post(
    "/{project_uuid}/project-info/run",
    response_model=ProjectInfoJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_project_info(
    project_uuid: UUID,
    payload: ProjectInfoRunRequest,
    service: ProjectInfoJobService = Depends(get_writable_project_info_job_service),
) -> ProjectInfoJobRead:
    """Queue a project-info run; returns the open job instead when one is queued or
    running."""
    job = await service.request_run(project_uuid, overwrite=payload.overwrite)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    return ProjectInfoJobRead.model_validate(job)
