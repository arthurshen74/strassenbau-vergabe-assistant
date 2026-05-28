from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.project_documents import project_documents
from shared.domain.project_document import NewProjectDocument, ProjectDocument


class ProjectDocumentRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, project_document_uuid: UUID) -> ProjectDocument | None:
        row = (
            await self.conn.execute(
                select(project_documents).where(
                    project_documents.c.project_document_uuid == project_document_uuid
                )
            )
        ).mappings().first()
        return ProjectDocument.model_validate(dict(row)) if row else None

    async def list_by_project(
        self, project_uuid: UUID
    ) -> Sequence[ProjectDocument]:
        stmt = (
            select(project_documents)
            .where(project_documents.c.project_uuid == project_uuid)
            .order_by(project_documents.c.ingested_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [ProjectDocument.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewProjectDocument) -> ProjectDocument:
        stmt = (
            insert(project_documents)
            .values(**new.model_dump())
            .returning(project_documents)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return ProjectDocument.model_validate(dict(row))

    async def delete(self, project_document_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(project_documents).where(
                project_documents.c.project_document_uuid == project_document_uuid
            )
        )
        return result.rowcount > 0
