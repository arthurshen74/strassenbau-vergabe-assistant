"""Read surface for the prompt execution log: filtered summaries for the table and a
full row for the detail view."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared.models.prompt_execution_log_schema import (
    PromptExecutionLogRead,
    PromptExecutionLogSummary,
)
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository


class PromptExecutionLogService:
    def __init__(self, repo: PromptExecutionLogRepository) -> None:
        self.repo = repo

    async def list_summaries(
        self,
        *,
        prompt_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PromptExecutionLogSummary]:
        rows = await self.repo.list(
            prompt_type=prompt_type, start=start, end=end, limit=limit, offset=offset
        )
        return [PromptExecutionLogSummary.model_validate(r) for r in rows]

    async def get(self, log_uuid: UUID) -> PromptExecutionLogRead | None:
        found = await self.repo.get(log_uuid)
        return PromptExecutionLogRead.model_validate(found) if found else None
