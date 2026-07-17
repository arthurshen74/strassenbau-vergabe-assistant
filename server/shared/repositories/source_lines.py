from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.source_lines import source_lines
from shared.models.source_line import NewSourceLine, SourceLine


class SourceLineRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, lines: list[NewSourceLine]) -> list[SourceLine]:
        """Bulk upsert on the (document_uuid, line_id) natural key; re-ingestion replays
        the SourceLines for a document, so a replay updates in place."""
        if not lines:
            return []
        stmt = pg_insert(source_lines).values([line.model_dump() for line in lines])
        stmt = stmt.on_conflict_do_update(
            index_elements=["document_uuid", "line_id"],
            set_={
                "page": stmt.excluded.page,
                "bbox": stmt.excluded.bbox,
                "line_text": stmt.excluded.line_text,
            },
        ).returning(source_lines)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [SourceLine.model_validate(dict(r)) for r in rows]

    async def list_by_document(self, document_uuid: UUID) -> list[SourceLine]:
        stmt = (
            select(source_lines)
            .where(source_lines.c.document_uuid == document_uuid)
            .order_by(source_lines.c.line_id)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [SourceLine.model_validate(dict(r)) for r in rows]
