from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.document_layout_regions import document_layout_regions
from shared.models.nlp import DocumentLayout, LayoutRegion


class DocumentLayoutRegionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(
        self, document_uuid: UUID, model_version: str
    ) -> DocumentLayout | None:
        stmt = select(document_layout_regions).where(
            document_layout_regions.c.document_uuid == document_uuid,
            document_layout_regions.c.model_version == model_version,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        if row is None:
            return None
        return DocumentLayout(
            document_uuid=row["document_uuid"],
            model_version=row["model_version"],
            regions=[LayoutRegion.model_validate(r) for r in row["regions"]],
        )

    async def put(self, layout: DocumentLayout) -> None:
        # Concurrent analyses may infer the same document; the first writer wins.
        stmt = pg_insert(document_layout_regions).values(
            document_uuid=layout.document_uuid,
            model_version=layout.model_version,
            regions=[r.model_dump() for r in layout.regions],
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["document_uuid", "model_version"]
        )
        await self.conn.execute(stmt)
