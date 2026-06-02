from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection
from shared.models.enums import UsageOperation
from shared.models.openrouter_usage_schema import OpenRouterUsageRead
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.services.usage_log_service import UsageLogService

router = APIRouter(prefix="/usage", tags=["usage"])


def get_service(
    conn: AsyncConnection = Depends(get_connection),
) -> UsageLogService:
    return UsageLogService(OpenRouterUsageRepository(conn))


@router.get("", response_model=list[OpenRouterUsageRead])
async def list_usage(
    operation: UsageOperation | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: UsageLogService = Depends(get_service),
) -> list[OpenRouterUsageRead]:
    return await service.list(
        operation=operation, start=start, end=end, limit=limit, offset=offset
    )
