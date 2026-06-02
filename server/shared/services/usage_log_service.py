"""Read surface for the OpenRouter usage log: filtered listing for the table."""

from __future__ import annotations

from datetime import datetime

from shared.models.enums import UsageOperation
from shared.models.openrouter_usage_schema import OpenRouterUsageRead
from shared.repositories.openrouter_usage import OpenRouterUsageRepository


class UsageLogService:
    def __init__(self, repo: OpenRouterUsageRepository) -> None:
        self.repo = repo

    async def list(
        self,
        *,
        operation: UsageOperation | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OpenRouterUsageRead]:
        rows = await self.repo.list(
            operation=operation, start=start, end=end, limit=limit, offset=offset
        )
        return [OpenRouterUsageRead.model_validate(r) for r in rows]
