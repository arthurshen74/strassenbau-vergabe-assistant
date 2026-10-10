from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import Principal, get_current_user, get_engine
from api.sse import SSE_HEARTBEAT, SSE_MEDIA_TYPE, format_sse
from shared.config import settings
from shared.models.enums import IngestStatus
from shared.models.ingest_schema import ConsoleJobRead, IngestJobRead
from shared.models.project_info_schema import ProjectInfoJobRead
from shared.services.ingest_admin import (
    IngestAdminService,
    stream_console_jobs,
    stream_job_activity,
    stream_project_info_activity,
)
from shared.services.ingestion.status_stream import HEARTBEAT

router = APIRouter(prefix="/ingest-jobs", tags=["ingest-jobs"])


def get_ingest_admin_service(
    engine: AsyncEngine = Depends(get_engine),
) -> IngestAdminService:
    return IngestAdminService(engine)


def _sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in events:
            yield SSE_HEARTBEAT if event.get(HEARTBEAT) else format_sse(event)

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)


@router.get("", response_model=list[ConsoleJobRead])
async def list_ingest_jobs(
    status: Annotated[list[IngestStatus] | None, Query()] = None,
    project_uuid: UUID | None = None,
    active: bool = False,
    _principal: Principal = Depends(get_current_user),
    service: IngestAdminService = Depends(get_ingest_admin_service),
) -> list[ConsoleJobRead]:
    """Ingest and Projektinfo jobs, newest first. `active` keeps open jobs and jobs
    finished in the last few minutes."""
    jobs = await service.list_jobs(
        statuses=status, project_uuid=project_uuid, active=active
    )
    return [ConsoleJobRead.model_validate(job) for job in jobs]


@router.get("/stream")
async def stream_ingest_jobs(
    status: Annotated[list[IngestStatus] | None, Query()] = None,
    project_uuid: UUID | None = None,
    active: bool = False,
    _principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> StreamingResponse:
    """Stream the console list as SSE: a ConsoleJobsSnapshot on connect and whenever
    the filtered list changes."""
    return _sse(
        stream_console_jobs(
            engine,
            statuses=status,
            project_uuid=project_uuid,
            active=active,
            poll_interval=settings.ingest_status_poll_interval_seconds,
        )
    )


@router.post("/{job_uuid}/requeue", response_model=IngestJobRead)
async def requeue_ingest_job(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    service: IngestAdminService = Depends(get_ingest_admin_service),
) -> IngestJobRead:
    """Reset a stuck/failed job in place to QUEUED so the worker reprocesses it."""
    job = await service.requeue(job_uuid)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="ingest job not found"
        )
    return IngestJobRead.model_validate(job)


@router.get("/{job_uuid}/activity/stream")
async def stream_ingest_job_activity(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> StreamingResponse:
    """Stream a job's granular activity lines as SSE for the live console terminal."""
    return _sse(
        stream_job_activity(
            engine, job_uuid, poll_interval=settings.ingest_status_poll_interval_seconds
        )
    )


@router.post("/project-info/{job_uuid}/requeue", response_model=ProjectInfoJobRead)
async def requeue_project_info_job(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    service: IngestAdminService = Depends(get_ingest_admin_service),
) -> ProjectInfoJobRead:
    """Reset a stuck/failed Projektinfo job in place to QUEUED so the worker reruns
    it."""
    job = await service.requeue_project_info(job_uuid)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="project-info job not found",
        )
    return ProjectInfoJobRead.model_validate(job)


@router.get("/project-info/{job_uuid}/activity/stream")
async def stream_project_info_job_activity(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> StreamingResponse:
    """Stream a Projektinfo job's activity lines as SSE for the live console
    terminal."""
    return _sse(
        stream_project_info_activity(
            engine, job_uuid, poll_interval=settings.ingest_status_poll_interval_seconds
        )
    )
