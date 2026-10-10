from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.project_info_activity_log import project_info_activity_log
from shared.models.project_info_activity import (
    NewProjectInfoActivity,
    ProjectInfoActivity,
)


class ProjectInfoActivityLogRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, rows: list[NewProjectInfoActivity]) -> int:
        """Bulk-append activity lines (one executemany INSERT)."""
        if not rows:
            return 0
        await self.conn.execute(
            insert(project_info_activity_log), [r.model_dump() for r in rows]
        )
        return len(rows)

    async def tail(
        self, job_uuid: UUID, after_id: int, limit: int
    ) -> list[ProjectInfoActivity]:
        """Activity lines for a job with id greater than the cursor, oldest first."""
        stmt = (
            select(project_info_activity_log)
            .where(
                project_info_activity_log.c.job_uuid == job_uuid,
                project_info_activity_log.c.id > after_id,
            )
            .order_by(project_info_activity_log.c.id)
            .limit(limit)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [ProjectInfoActivity.model_validate(dict(r)) for r in rows]

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Delete activity lines older than the cutoff. Returns the number deleted."""
        result = await self.conn.execute(
            delete(project_info_activity_log).where(
                project_info_activity_log.c.ts < cutoff
            )
        )
        return result.rowcount
