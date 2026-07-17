from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.conversations import conversations
from shared.models.conversation import Conversation, NewConversation
from shared.models.enums import CalculationStatus


class ConversationRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewConversation) -> Conversation:
        stmt = insert(conversations).values(**new.model_dump()).returning(conversations)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Conversation.model_validate(dict(row))

    async def get(self, conversation_uuid: UUID) -> Conversation | None:
        stmt = select(conversations).where(
            conversations.c.conversation_uuid == conversation_uuid
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Conversation.model_validate(dict(row)) if row else None

    async def list_by_user(self, user_uuid: UUID) -> list[Conversation]:
        stmt = (
            select(conversations)
            .where(conversations.c.user_uuid == user_uuid)
            .order_by(conversations.c.updated_at.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Conversation.model_validate(dict(r)) for r in rows]

    async def set_title(
        self, conversation_uuid: UUID, title: str
    ) -> Conversation | None:
        stmt = (
            update(conversations)
            .where(conversations.c.conversation_uuid == conversation_uuid)
            .values(title=title, updated_at=func.now())
            .returning(conversations)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Conversation.model_validate(dict(row)) if row else None

    async def touch(self, conversation_uuid: UUID) -> None:
        """Bump updated_at so the conversation re-sorts to the top of the list."""
        stmt = (
            update(conversations)
            .where(conversations.c.conversation_uuid == conversation_uuid)
            .values(updated_at=func.now())
        )
        await self.conn.execute(stmt)

    async def set_calculation_status(
        self, conversation_uuid: UUID, status: CalculationStatus
    ) -> None:
        """Move an ekt_calculator conversation through its run lifecycle."""
        stmt = (
            update(conversations)
            .where(conversations.c.conversation_uuid == conversation_uuid)
            .values(calculation_status=status, updated_at=func.now())
        )
        await self.conn.execute(stmt)

    async def delete(self, conversation_uuid: UUID) -> bool:
        """Delete a conversation; its messages cascade (messages FK ON DELETE CASCADE).
        Returns whether a row was removed."""
        stmt = (
            delete(conversations)
            .where(conversations.c.conversation_uuid == conversation_uuid)
            .returning(conversations.c.conversation_uuid)
        )
        return (await self.conn.execute(stmt)).first() is not None
