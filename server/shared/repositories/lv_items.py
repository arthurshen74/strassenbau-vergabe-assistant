from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.batching import insert_batches
from shared.db.tables.documents import LV_DOCUMENT_ORDER, documents
from shared.db.tables.lv_items import lv_items
from shared.models.enums import DocumentType
from shared.models.lv_item import LVItem, NewLVItem

# Natural key the LV parse output upserts on; everything else is overwritten on
# conflict.
LV_NATURAL_KEY = ("document_uuid", "oz")
COL_LAST_INGESTION = "last_ingestion"


class LVItemRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, lv_item_uuid: UUID) -> LVItem | None:
        row = (
            (
                await self.conn.execute(
                    select(lv_items).where(lv_items.c.lv_item_uuid == lv_item_uuid)
                )
            )
            .mappings()
            .first()
        )
        return LVItem.model_validate(dict(row)) if row else None

    async def get_by_project_and_oz(self, project_uuid: UUID, oz: str) -> LVItem | None:
        """Backs the LV_Item_Lookup gate. The unique key is (document_uuid, oz), so with
        several LV documents an oz can match more than once; this returns the first
        match in document order (see list_by_project_and_oz for all of them)."""
        matches = await self.list_by_project_and_oz(project_uuid, oz)
        return matches[0] if matches else None

    async def list_by_project_and_oz(self, project_uuid: UUID, oz: str) -> list[LVItem]:
        """Every position with this oz across the project's LV documents, in document
        order."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == DocumentType.LV_DOCUMENT,
                lv_items.c.oz == oz,
            )
            .order_by(*LV_DOCUMENT_ORDER)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

    async def list_by_project(self, project_uuid: UUID) -> list[LVItem]:
        """All LV items across the project's LV documents, grouped by document (oldest
        first) and ordered by oz within each."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == DocumentType.LV_DOCUMENT,
            )
            .order_by(*LV_DOCUMENT_ORDER, lv_items.c.oz)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

    async def list_by_document(self, document_uuid: UUID) -> list[LVItem]:
        """One document's LV items ordered by oz; empty for a prose document."""
        stmt = (
            select(lv_items)
            .where(lv_items.c.document_uuid == document_uuid)
            .order_by(lv_items.c.oz)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

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

    async def list_by_uuids(self, lv_item_uuids: Sequence[UUID]) -> list[LVItem]:
        """LV items for the given uuids in arbitrary order; the caller re-orders by
        relevance. Backs hybrid LV item search, which ranks lv_item_uuids in
        Elasticsearch then loads the rows."""
        if not lv_item_uuids:
            return []
        stmt = select(lv_items).where(lv_items.c.lv_item_uuid.in_(list(lv_item_uuids)))
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

    async def list_uuids_by_document(self, document_uuid: UUID) -> list[UUID]:
        """LV item UUIDs for a document; empty for a non-LV document. Targets the ES
        LV_ITEM chunks (keyed by lv_item_uuid) when the document is deleted, before the
        cascade removes the rows."""
        stmt = select(lv_items.c.lv_item_uuid).where(
            lv_items.c.document_uuid == document_uuid
        )
        rows = (await self.conn.execute(stmt)).scalars().all()
        return list(rows)

    async def add(self, new: NewLVItem) -> LVItem:
        stmt = insert(lv_items).values(**new.model_dump()).returning(lv_items)
        row = (await self.conn.execute(stmt)).mappings().one()
        return LVItem.model_validate(dict(row))

    async def add_many(self, items: Sequence[NewLVItem]) -> list[LVItem]:
        """Bulk upsert the LV parse output on the (document_uuid, oz) natural key,
        bumping last_ingestion. A re-ingestion replays a document's LV items and updates
        them in place, so each lv_item_uuid stays stable and its Elasticsearch chunks
        (keyed by that uuid) remain addressable for re-archival."""
        result: list[LVItem] = []
        for batch in insert_batches(lv_items, items):
            stmt = pg_insert(lv_items).values(batch)
            overwrite = {
                name: stmt.excluded[name]
                for name in NewLVItem.model_fields
                if name not in LV_NATURAL_KEY
            }
            overwrite[COL_LAST_INGESTION] = func.now()
            stmt = stmt.on_conflict_do_update(
                index_elements=list(LV_NATURAL_KEY), set_=overwrite
            ).returning(lv_items)
            rows = (await self.conn.execute(stmt)).mappings().all()
            result.extend(LVItem.model_validate(dict(r)) for r in rows)
        return result

    async def delete_missing(
        self, document_uuid: UUID, keep_ozs: Sequence[str]
    ) -> list[UUID]:
        """Delete a document's LV items whose oz is not in keep_ozs, returning the
        removed lv_item_uuids so the caller can archive their Elasticsearch chunks. Used
        by re-ingestion to drop positions that no longer appear; an empty keep_ozs
        removes all."""
        condition = lv_items.c.document_uuid == document_uuid
        if keep_ozs:
            condition = condition & lv_items.c.oz.notin_(keep_ozs)
        stmt = delete(lv_items).where(condition).returning(lv_items.c.lv_item_uuid)
        return list((await self.conn.execute(stmt)).scalars().all())
