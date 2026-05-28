from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.project_document_types import project_document_types
from shared.domain.project_document_type import (
    NewProjectDocumentType,
    ProjectDocumentType,
)


class ProjectDocumentTypeRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, document_type_uuid: UUID) -> ProjectDocumentType | None:
        row = (
            await self.conn.execute(
                select(project_document_types).where(
                    project_document_types.c.document_type_uuid == document_type_uuid
                )
            )
        ).mappings().first()
        return ProjectDocumentType.model_validate(dict(row)) if row else None

    async def get_by_type(self, document_type: str) -> ProjectDocumentType | None:
        row = (
            await self.conn.execute(
                select(project_document_types).where(
                    project_document_types.c.document_type == document_type
                )
            )
        ).mappings().first()
        return ProjectDocumentType.model_validate(dict(row)) if row else None

    async def list(self) -> Sequence[ProjectDocumentType]:
        stmt = select(project_document_types).order_by(
            project_document_types.c.document_type
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [ProjectDocumentType.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewProjectDocumentType) -> ProjectDocumentType:
        stmt = (
            insert(project_document_types)
            .values(**new.model_dump())
            .returning(project_document_types)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return ProjectDocumentType.model_validate(dict(row))

    async def delete(self, document_type_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(project_document_types).where(
                project_document_types.c.document_type_uuid == document_type_uuid
            )
        )
        return result.rowcount > 0
