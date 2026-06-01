from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.thumbnails import thumbnails
from shared.models.thumbnail import NewThumbnail, Thumbnail


class ThumbnailRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewThumbnail) -> Thumbnail:
        stmt = insert(thumbnails).values(**new.model_dump()).returning(thumbnails)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Thumbnail.model_validate(dict(row))

    async def list_by_document(self, document_uuid: UUID) -> list[Thumbnail]:
        stmt = (
            select(thumbnails)
            .where(thumbnails.c.document_uuid == document_uuid)
            .order_by(thumbnails.c.page_number)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Thumbnail.model_validate(dict(r)) for r in rows]
