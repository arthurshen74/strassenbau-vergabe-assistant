from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.document_thumbnails import document_thumbnails
from shared.domain.document_thumbnail import DocumentThumbnail, NewDocumentThumbnail


class DocumentThumbnailRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, thumbnail_uuid: UUID) -> DocumentThumbnail | None:
        row = (
            await self.conn.execute(
                select(document_thumbnails).where(
                    document_thumbnails.c.thumbnail_uuid == thumbnail_uuid
                )
            )
        ).mappings().first()
        return DocumentThumbnail.model_validate(dict(row)) if row else None

    async def list_by_document(
        self, project_document_uuid: UUID
    ) -> Sequence[DocumentThumbnail]:
        stmt = (
            select(document_thumbnails)
            .where(
                document_thumbnails.c.project_document_uuid == project_document_uuid
            )
            .order_by(document_thumbnails.c.page_number)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [DocumentThumbnail.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewDocumentThumbnail) -> DocumentThumbnail:
        stmt = (
            insert(document_thumbnails)
            .values(**new.model_dump())
            .returning(document_thumbnails)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return DocumentThumbnail.model_validate(dict(row))

    async def delete(self, thumbnail_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(document_thumbnails).where(
                document_thumbnails.c.thumbnail_uuid == thumbnail_uuid
            )
        )
        return result.rowcount > 0
