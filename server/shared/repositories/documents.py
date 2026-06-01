from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.models.document import Document, NewDocument
from shared.models.enums import DocumentType


class DocumentRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewDocument) -> Document:
        stmt = insert(documents).values(**new.model_dump()).returning(documents)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Document.model_validate(dict(row))

    async def get(self, document_uuid: UUID) -> Document | None:
        stmt = select(documents).where(documents.c.document_uuid == document_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return Document.model_validate(dict(row)) if row else None

    async def list_by_project(self, project_uuid: UUID) -> list[Document]:
        stmt = (
            select(documents)
            .where(documents.c.project_uuid == project_uuid)
            .order_by(documents.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Document.model_validate(dict(r)) for r in rows]

    async def get_lv_document(self, project_uuid: UUID) -> Document | None:
        """The project's single LV document. Backs the RETRIEVAL "Plus" filter and
        the LV-item chat gate; the partial unique index guarantees at most one."""
        stmt = select(documents).where(
            documents.c.project_uuid == project_uuid,
            documents.c.document_type == DocumentType.LV_DOCUMENT,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Document.model_validate(dict(row)) if row else None

    async def delete(self, document_uuid: UUID) -> None:
        stmt = delete(documents).where(documents.c.document_uuid == document_uuid)
        await self.conn.execute(stmt)
