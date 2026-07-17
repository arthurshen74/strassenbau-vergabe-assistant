from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.prompt_execution_log import prompt_execution_log
from shared.models.prompt_execution_log import (
    NewPromptExecutionLog,
    PromptExecutionLog,
)


class PromptExecutionLogRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewPromptExecutionLog) -> PromptExecutionLog:
        stmt = (
            insert(prompt_execution_log)
            .values(**new.model_dump())
            .returning(prompt_execution_log)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return PromptExecutionLog.model_validate(dict(row))

    async def get(self, log_uuid: UUID) -> PromptExecutionLog | None:
        stmt = select(prompt_execution_log).where(
            prompt_execution_log.c.log_uuid == log_uuid
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return PromptExecutionLog.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> list[PromptExecutionLog]:
        stmt = (
            select(prompt_execution_log)
            .where(prompt_execution_log.c.project_uuid == project_uuid)
            .order_by(prompt_execution_log.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [PromptExecutionLog.model_validate(dict(r)) for r in rows]

    async def list(
        self,
        *,
        prompt_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PromptExecutionLog]:
        """Most-recent-first execution logs, optionally filtered by prompt type and date
        range."""
        stmt = select(prompt_execution_log)
        if prompt_type is not None:
            stmt = stmt.where(prompt_execution_log.c.prompt_type == prompt_type)
        if start is not None:
            stmt = stmt.where(prompt_execution_log.c.created_at >= start)
        if end is not None:
            stmt = stmt.where(prompt_execution_log.c.created_at < end)
        stmt = (
            stmt.order_by(prompt_execution_log.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [PromptExecutionLog.model_validate(dict(r)) for r in rows]
