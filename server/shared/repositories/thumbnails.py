from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.batching import insert_batches
from shared.db.tables.thumbnails import thumbnails
from shared.models.thumbnail import NewThumbnail, Thumbnail


class ThumbnailRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewThumbnail) -> Thumbnail:
        stmt = insert(thumbnails).values(**new.model_dump()).returning(thumbnails)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Thumbnail.model_validate(dict(row))

    async def add_many(self, items: Sequence[NewThumbnail]) -> list[Thumbnail]:
        """Bulk upsert on the (document_uuid, page_number) natural key; a re-ingestion
        replays a document's page thumbnails and updates them in place."""
        result: list[Thumbnail] = []
        for batch in insert_batches(thumbnails, items):
            stmt = pg_insert(thumbnails).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["document_uuid", "page_number"],
                set_={
                    "object_key": stmt.excluded.object_key,
                    "bucket": stmt.excluded.bucket,
                    "width": stmt.excluded.width,
                    "height": stmt.excluded.height,
                    "content_type": stmt.excluded.content_type,
                },
            ).returning(thumbnails)
            rows = (await self.conn.execute(stmt)).mappings().all()
            result.extend(Thumbnail.model_validate(dict(r)) for r in rows)
        return result

    async def get_by_page(
        self, document_uuid: UUID, page_number: int
    ) -> Thumbnail | None:
        stmt = select(thumbnails).where(
            thumbnails.c.document_uuid == document_uuid,
            thumbnails.c.page_number == page_number,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Thumbnail.model_validate(dict(row)) if row else None

    async def list_by_document(self, document_uuid: UUID) -> list[Thumbnail]:
        stmt = (
            select(thumbnails)
            .where(thumbnails.c.document_uuid == document_uuid)
            .order_by(thumbnails.c.page_number)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Thumbnail.model_validate(dict(r)) for r in rows]
