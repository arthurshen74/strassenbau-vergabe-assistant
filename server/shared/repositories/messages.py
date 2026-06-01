from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.messages import messages
from shared.models.message import Message, NewMessage


class MessageRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewMessage) -> Message:
        stmt = insert(messages).values(**new.model_dump()).returning(messages)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Message.model_validate(dict(row))

    async def list_for_conversation(self, conversation_uuid: UUID) -> list[Message]:
        stmt = (
            select(messages)
            .where(messages.c.conversation_uuid == conversation_uuid)
            .order_by(messages.c.created_at)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Message.model_validate(dict(r)) for r in rows]
