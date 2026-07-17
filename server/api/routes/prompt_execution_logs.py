from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection
from shared.models.prompt_execution_log_schema import (
    PromptExecutionLogRead,
    PromptExecutionLogSummary,
)
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository
from shared.services.prompt_execution_log_service import PromptExecutionLogService

router = APIRouter(prefix="/prompt-execution-logs", tags=["prompt-execution-logs"])


def get_service(
    conn: AsyncConnection = Depends(get_connection),
) -> PromptExecutionLogService:
    return PromptExecutionLogService(PromptExecutionLogRepository(conn))


@router.get("", response_model=list[PromptExecutionLogSummary])
async def list_execution_logs(
    prompt_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: PromptExecutionLogService = Depends(get_service),
) -> list[PromptExecutionLogSummary]:
    return await service.list_summaries(
        prompt_type=prompt_type, start=start, end=end, limit=limit, offset=offset
    )


@router.get("/{log_uuid}", response_model=PromptExecutionLogRead)
async def get_execution_log(
    log_uuid: UUID,
    service: PromptExecutionLogService = Depends(get_service),
) -> PromptExecutionLogRead:
    found = await service.get(log_uuid)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="log not found"
        )
    return found
