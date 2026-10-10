from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.batching import insert_batches
from shared.db.tables.documents import LV_DOCUMENT_ORDER, documents
from shared.db.tables.lv_texts import lv_texts
from shared.models.enums import DocumentType
from shared.models.lv_text import LVText, NewLVText


class LVTextRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def list_by_document(self, document_uuid: UUID) -> list[LVText]:
        stmt = (
            select(lv_texts)
            .where(lv_texts.c.document_uuid == document_uuid)
            .order_by(lv_texts.c.sequence)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVText.model_validate(dict(r)) for r in rows]

    async def list_by_project(self, project_uuid: UUID) -> list[LVText]:
        """All LV texts across the project's LV documents, grouped by document (oldest
        first) and in sequence within each."""
        stmt = (
            select(lv_texts)
            .join(documents, documents.c.document_uuid == lv_texts.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == DocumentType.LV_DOCUMENT,
            )
            .order_by(*LV_DOCUMENT_ORDER, lv_texts.c.sequence)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVText.model_validate(dict(r)) for r in rows]

    async def list_uuids_by_document(self, document_uuid: UUID) -> list[UUID]:
        """LV text UUIDs for a document; they key the ES LV_TEXT chunks, which must be
        archived before the cascade removes the rows."""
        stmt = select(lv_texts.c.lv_text_uuid).where(
            lv_texts.c.document_uuid == document_uuid
        )
        return list((await self.conn.execute(stmt)).scalars().all())

    async def replace(
        self, document_uuid: UUID, texts: Sequence[NewLVText]
    ) -> tuple[list[LVText], list[UUID]]:
        """Replace a document's LV texts wholesale. There is no natural key to upsert on
        (a re-parse may renumber the nodes), so the prior rows are deleted and their
        uuids returned for chunk archival, then the new rows inserted in order."""
        removed = list(
            (
                await self.conn.execute(
                    delete(lv_texts)
                    .where(lv_texts.c.document_uuid == document_uuid)
                    .returning(lv_texts.c.lv_text_uuid)
                )
            )
            .scalars()
            .all()
        )
        created: list[LVText] = []
        for batch in insert_batches(lv_texts, texts):
            stmt = insert(lv_texts).values(batch).returning(lv_texts)
            rows = (await self.conn.execute(stmt)).mappings().all()
            created.extend(LVText.model_validate(dict(r)) for r in rows)
        created.sort(key=lambda t: t.sequence)
        return created, removed
