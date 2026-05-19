from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.questions import questions
from shared.domain.question import (
    NewQuestion,
    Question,
    QuestionCategory,
    QuestionType,
)


class QuestionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, question_uuid: UUID) -> Question | None:
        row = (
            await self.conn.execute(
                select(questions).where(questions.c.question_uuid == question_uuid)
            )
        ).mappings().first()
        return Question.model_validate(dict(row)) if row else None

    async def list(
        self,
        *,
        question_category: QuestionCategory | None = None,
        question_type: QuestionType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Question]:
        stmt = select(questions)
        if question_category is not None:
            stmt = stmt.where(questions.c.question_category == question_category.value)
        if question_type is not None:
            stmt = stmt.where(questions.c.question_type == question_type.value)
        stmt = stmt.order_by(questions.c.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Question.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewQuestion) -> Question:
        stmt = insert(questions).values(**new.model_dump()).returning(questions)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Question.model_validate(dict(row))

    async def update(self, question_uuid: UUID, **changes: Any) -> Question | None:
        if not changes:
            return await self.get(question_uuid)
        stmt = (
            update(questions)
            .where(questions.c.question_uuid == question_uuid)
            .values(**changes)
            .returning(questions)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Question.model_validate(dict(row)) if row else None

    async def delete(self, question_uuid: UUID) -> bool:
        result = await self.conn.execute(
            delete(questions).where(questions.c.question_uuid == question_uuid)
        )
        return result.rowcount > 0
