from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.openrouter_usage import openrouter_usage
from shared.models.enums import UsageOperation
from shared.models.openrouter_usage import NewOpenRouterUsage, OpenRouterUsage


class OpenRouterUsageRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewOpenRouterUsage) -> OpenRouterUsage:
        stmt = insert(openrouter_usage).values(**new.model_dump()).returning(openrouter_usage)
        row = (await self.conn.execute(stmt)).mappings().one()
        return OpenRouterUsage.model_validate(dict(row))

    async def get(self, usage_uuid: UUID) -> OpenRouterUsage | None:
        stmt = select(openrouter_usage).where(openrouter_usage.c.usage_uuid == usage_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return OpenRouterUsage.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> list[OpenRouterUsage]:
        stmt = (
            select(openrouter_usage)
            .where(openrouter_usage.c.project_uuid == project_uuid)
            .order_by(openrouter_usage.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [OpenRouterUsage.model_validate(dict(r)) for r in rows]

    async def list_by_ingest_job(self, ingest_job_uuid: UUID) -> list[OpenRouterUsage]:
        stmt = (
            select(openrouter_usage)
            .where(openrouter_usage.c.ingest_job_uuid == ingest_job_uuid)
            .order_by(openrouter_usage.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [OpenRouterUsage.model_validate(dict(r)) for r in rows]

    async def sum_cost_by_conversation(self, conversation_uuid: UUID) -> Decimal:
        """Total USD cost attributed to a conversation (zero if none recorded)."""
        stmt = select(func.coalesce(func.sum(openrouter_usage.c.cost), 0)).where(
            openrouter_usage.c.conversation_uuid == conversation_uuid
        )
        return (await self.conn.execute(stmt)).scalar_one()

    async def sum_cost_by_document(self, document_uuid: UUID) -> Decimal:
        """Total USD cost attributed to a document's ingestion (zero if none recorded)."""
        stmt = select(func.coalesce(func.sum(openrouter_usage.c.cost), 0)).where(
            openrouter_usage.c.document_uuid == document_uuid
        )
        return (await self.conn.execute(stmt)).scalar_one()

    async def list(
        self,
        *,
        operation: UsageOperation | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OpenRouterUsage]:
        """Most-recent-first usage rows, optionally filtered by operation and date range."""
        stmt = select(openrouter_usage)
        if operation is not None:
            stmt = stmt.where(openrouter_usage.c.operation == operation)
        if start is not None:
            stmt = stmt.where(openrouter_usage.c.created_at >= start)
        if end is not None:
            stmt = stmt.where(openrouter_usage.c.created_at < end)
        stmt = (
            stmt.order_by(openrouter_usage.c.created_at.desc()).limit(limit).offset(offset)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [OpenRouterUsage.model_validate(dict(r)) for r in rows]
