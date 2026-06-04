from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, insert, select, union_all
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.ingestion_activity_log import ingestion_activity_log
from shared.db.tables.ingestion_activity_log_archive import ingestion_activity_log_archive
from shared.models.ingestion_activity import IngestionActivity, NewIngestionActivity


class IngestionActivityLogRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, rows: list[NewIngestionActivity]) -> int:
        """Bulk-append activity lines (one executemany INSERT)."""
        if not rows:
            return 0
        await self.conn.execute(
            insert(ingestion_activity_log), [r.model_dump() for r in rows]
        )
        return len(rows)

    async def tail(
        self, job_uuid: UUID, after_id: int, limit: int
    ) -> list[IngestionActivity]:
        """Activity lines for a job with id greater than the cursor, oldest first."""
        stmt = (
            select(ingestion_activity_log)
            .where(
                ingestion_activity_log.c.job_uuid == job_uuid,
                ingestion_activity_log.c.id > after_id,
            )
            .order_by(ingestion_activity_log.c.id)
            .limit(limit)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestionActivity.model_validate(dict(r)) for r in rows]

    async def list_for_document(
        self, document_uuid: UUID, *, offset: int = 0, limit: int = 200
    ) -> list[IngestionActivity]:
        """A document's activity, oldest first, across the active and archive tables (paged)."""
        active_q = select(ingestion_activity_log).where(
            ingestion_activity_log.c.document_uuid == document_uuid
        )
        archive_q = select(ingestion_activity_log_archive).where(
            ingestion_activity_log_archive.c.document_uuid == document_uuid
        )
        combined = union_all(active_q, archive_q).subquery()
        stmt = select(combined).order_by(combined.c.id).limit(limit).offset(offset)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [IngestionActivity.model_validate(dict(r)) for r in rows]

    async def archive_stale(self, older_than: datetime) -> int:
        """Move activity lines older than the cutoff from the active table into the archive,
        preserving their ids, so the hot table stays small while history is kept. Returns the
        number moved. Caller runs this in a transaction so the copy and delete commit together."""
        columns = [c.name for c in ingestion_activity_log.c]
        moved = await self.conn.execute(
            insert(ingestion_activity_log_archive).from_select(
                columns,
                select(ingestion_activity_log).where(
                    ingestion_activity_log.c.ts < older_than
                ),
            )
        )
        await self.conn.execute(
            delete(ingestion_activity_log).where(ingestion_activity_log.c.ts < older_than)
        )
        return moved.rowcount
