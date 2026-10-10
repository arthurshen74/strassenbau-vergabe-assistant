from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.batching import insert_batches
from shared.db.tables.form_fields import form_fields
from shared.models.form_field import FormField, NewFormField


class FormFieldRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add_many(self, fields: list[NewFormField]) -> list[FormField]:
        result: list[FormField] = []
        for batch in insert_batches(form_fields, fields):
            stmt = insert(form_fields).values(batch).returning(form_fields)
            rows = (await self.conn.execute(stmt)).mappings().all()
            result.extend(FormField.model_validate(dict(r)) for r in rows)
        return result

    async def list_for_document(self, document_uuid: UUID) -> list[FormField]:
        stmt = (
            select(form_fields)
            .where(form_fields.c.document_uuid == document_uuid)
            .order_by(form_fields.c.field_order)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [FormField.model_validate(dict(r)) for r in rows]

    async def delete_for_document(self, document_uuid: UUID) -> int:
        result = await self.conn.execute(
            delete(form_fields).where(form_fields.c.document_uuid == document_uuid)
        )
        return result.rowcount
