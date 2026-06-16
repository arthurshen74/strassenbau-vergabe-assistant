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
from shared.models.ingest_schema import IngestJobConsoleRead
from shared.services.ingest_admin import IngestAdminService, stream_job_activity
from shared.services.ingestion.status_stream import HEARTBEAT

router = APIRouter(prefix="/ingest-jobs", tags=["ingest-jobs"])


def get_ingest_admin_service(
    engine: AsyncEngine = Depends(get_engine),
) -> IngestAdminService:
    return IngestAdminService(engine)


@router.get("", response_model=list[IngestJobConsoleRead])
async def list_ingest_jobs(
    status: Annotated[list[IngestStatus] | None, Query()] = None,
    project_uuid: UUID | None = None,
    _principal: Principal = Depends(get_current_user),
    service: IngestAdminService = Depends(get_ingest_admin_service),
) -> list[IngestJobConsoleRead]:
    jobs = await service.list_jobs(statuses=status, project_uuid=project_uuid)
    return [IngestJobConsoleRead.model_validate(job) for job in jobs]


@router.post("/{job_uuid}/requeue", response_model=IngestJobConsoleRead)
async def requeue_ingest_job(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    service: IngestAdminService = Depends(get_ingest_admin_service),
) -> IngestJobConsoleRead:
    """Reset a stuck/failed job in place to QUEUED so the worker reprocesses it."""
    job = await service.requeue(job_uuid)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="ingest job not found"
        )
    return IngestJobConsoleRead.model_validate(job)


@router.get("/{job_uuid}/activity/stream")
async def stream_ingest_job_activity(
    job_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> StreamingResponse:
    """Stream a job's granular activity lines as SSE for the live console terminal."""

    async def event_stream() -> AsyncIterator[str]:
        async for event in stream_job_activity(
            engine, job_uuid, poll_interval=settings.ingest_status_poll_interval_seconds
        ):
            yield SSE_HEARTBEAT if event.get(HEARTBEAT) else format_sse(event)

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)
