from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.db.tables.lv_items import lv_items
from shared.models.enums import DocumentType
from shared.models.lv_item import LVItem, NewLVItem


class LVItemRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, lv_item_uuid: UUID) -> LVItem | None:
        row = (
            await self.conn.execute(
                select(lv_items).where(lv_items.c.lv_item_uuid == lv_item_uuid)
            )
        ).mappings().first()
        return LVItem.model_validate(dict(row)) if row else None

    async def get_by_project_and_oz(
        self, project_uuid: UUID, oz: str
    ) -> LVItem | None:
        """Backs the LV_Item_Lookup gate. The schema's unique key is (document_uuid, oz),
        so a project+oz lookup resolves through the project's LV document."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == DocumentType.LV_DOCUMENT,
                lv_items.c.oz == oz,
            )
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return LVItem.model_validate(dict(row)) if row else None

    async def list_by_parent_oz(
        self, project_uuid: UUID, parent_oz: str
    ) -> list[LVItem]:
        """Backs the List_LV_Items_by_Parent_OZ gate."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == DocumentType.LV_DOCUMENT,
                lv_items.c.parent_oz == parent_oz,
            )
            .order_by(lv_items.c.oz)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewLVItem) -> LVItem:
        stmt = insert(lv_items).values(**new.model_dump()).returning(lv_items)
        row = (await self.conn.execute(stmt)).mappings().one()
        return LVItem.model_validate(dict(row))

    async def add_many(self, items: Sequence[NewLVItem]) -> list[LVItem]:
        """Bulk insert for the LV parse output. Relies on SQLAlchemy 2.0
        insertmanyvalues, which supports RETURNING for executemany."""
        if not items:
            return []
        rows = (
            await self.conn.execute(
                insert(lv_items).returning(lv_items),
                [item.model_dump() for item in items],
            )
        ).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]
