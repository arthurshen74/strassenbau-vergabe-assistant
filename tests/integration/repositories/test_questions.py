from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.question import (
    NewQuestion,
    Question,
    QuestionCategory,
    QuestionType,
)
from shared.repositories.questions import QuestionRepository


def _new(**overrides) -> NewQuestion:
    fields = dict(
        question_category=QuestionCategory.CALCULATOR,
        question_type=QuestionType.LOOKUP,
        question_text="Wie hoch ist die Bauzeit?",
    )
    fields.update(overrides)
    return NewQuestion(**fields)


async def test_add_round_trips_all_fields(conn: AsyncConnection) -> None:
    repo = QuestionRepository(conn)
    created = await repo.add(_new())

    assert created.question_uuid is not None
    assert created.question_category == QuestionCategory.CALCULATOR
    assert created.question_type == QuestionType.LOOKUP
    assert created.question_text == "Wie hoch ist die Bauzeit?"
    assert created.created_at is not None
    assert created.updated_at is not None


async def test_list_filters_by_category_and_type(conn: AsyncConnection) -> None:
    repo = QuestionRepository(conn)
    calc_lookup = await repo.add(_new())
    bauleiter_constraint = await repo.add(
        _new(
            question_category=QuestionCategory.BAULEITER,
            question_type=QuestionType.CONSTRAINT_SURFACING,
            question_text="Gibt es Arbeitszeitbeschränkungen?",
        )
    )

    by_cat = await repo.list(question_category=QuestionCategory.BAULEITER)
    assert {q.question_uuid for q in by_cat} == {bauleiter_constraint.question_uuid}

    by_type = await repo.list(question_type=QuestionType.LOOKUP)
    assert {q.question_uuid for q in by_type} == {calc_lookup.question_uuid}


async def test_check_constraint_rejects_unknown_category(
    conn: AsyncConnection,
) -> None:
    from shared.db.tables.questions import questions
    from sqlalchemy import insert

    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(questions).values(
                question_category="finance",
                question_type="lookup",
                question_text="x",
            )
        )


async def test_delete_removes_the_row(conn: AsyncConnection) -> None:
    repo = QuestionRepository(conn)
    created = await repo.add(_new())
    assert await repo.delete(created.question_uuid) is True
    assert await repo.get(created.question_uuid) is None


async def test_update_changes_text(conn: AsyncConnection) -> None:
    repo = QuestionRepository(conn)
    created = await repo.add(_new())
    updated = await repo.update(created.question_uuid, question_text="Neuer Text?")
    assert isinstance(updated, Question)
    assert updated.question_text == "Neuer Text?"


async def test_update_missing_returns_none(conn: AsyncConnection) -> None:
    repo = QuestionRepository(conn)
    assert await repo.update(uuid4(), question_text="ghost") is None
