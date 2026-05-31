from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.eval_item import AnswerType, NewEvalItem, TestType
from shared.domain.project import NewProject
from shared.domain.question import NewQuestion, QuestionCategory, QuestionType
from shared.repositories.eval_items import EvalItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.questions import QuestionRepository


async def _seed_question_and_project(conn: AsyncConnection):
    q = await QuestionRepository(conn).add(
        NewQuestion(
            question_category=QuestionCategory.CALCULATOR,
            question_type=QuestionType.LOOKUP,
            question_text="Wie hoch ist die Bauzeit?",
        )
    )
    p = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-EVAL-001",
            project_name="Eval Test Project",
            vergabestelle="Test Vergabestelle",
            project_location="Berlin",
        )
    )
    return q, p


async def test_add_context_retrieval_item(conn: AsyncConnection) -> None:
    q, p = await _seed_question_and_project(conn)
    repo = EvalItemRepository(conn)
    created = await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["Baubeschreibung", "ZTV"],
        )
    )
    assert created.eval_item_uuid is not None
    assert created.test_type == TestType.CONTEXT_RETRIEVAL
    assert created.answer_type is None
    assert created.expected_result == ["Baubeschreibung", "ZTV"]


async def test_add_numerical_answer_correctness_item(conn: AsyncConnection) -> None:
    q, p = await _seed_question_and_project(conn)
    repo = EvalItemRepository(conn)
    created = await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p.project_uuid,
            test_type=TestType.ANSWER_CORRECTNESS,
            answer_type=AnswerType.NUMERICAL,
            expected_result=12.5,
            numerical_tolerance=0.01,
        )
    )
    assert created.answer_type == AnswerType.NUMERICAL
    assert created.numerical_tolerance == 0.01
    assert created.expected_result == 12.5


async def test_list_by_project_returns_only_that_projects_items(
    conn: AsyncConnection,
) -> None:
    q, p_a = await _seed_question_and_project(conn)
    p_b = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-EVAL-002",
            project_name="B",
            vergabestelle="Test Vergabestelle",
            project_location="X",
        )
    )
    repo = EvalItemRepository(conn)
    a = await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p_a.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )
    await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p_b.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )

    listed = await repo.list_by_project(p_a.project_uuid)
    assert {i.eval_item_uuid for i in listed} == {a.eval_item_uuid}


async def test_list_by_question_returns_items_across_projects(
    conn: AsyncConnection,
) -> None:
    q, p_a = await _seed_question_and_project(conn)
    p_b = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-EVAL-003",
            project_name="B",
            vergabestelle="Test Vergabestelle",
            project_location="X",
        )
    )
    repo = EvalItemRepository(conn)
    a = await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p_a.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )
    b = await repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p_b.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )

    listed = await repo.list_by_question(q.question_uuid)
    assert {i.eval_item_uuid for i in listed} == {a.eval_item_uuid, b.eval_item_uuid}


async def test_check_constraint_rejects_unknown_test_type(
    conn: AsyncConnection,
) -> None:
    q, p = await _seed_question_and_project(conn)
    from shared.db.tables.eval_items import eval_items
    from sqlalchemy import insert

    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(eval_items).values(
                question_uuid=q.question_uuid,
                project_uuid=p.project_uuid,
                test_type="unknown_kind",
            )
        )


async def test_deleting_project_cascades_to_eval_items(
    conn: AsyncConnection,
) -> None:
    q, p = await _seed_question_and_project(conn)
    eval_repo = EvalItemRepository(conn)
    item = await eval_repo.add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )
    await ProjectRepository(conn).delete(p.project_uuid)
    assert await eval_repo.get(item.eval_item_uuid) is None


async def test_get_missing_returns_none(conn: AsyncConnection) -> None:
    assert await EvalItemRepository(conn).get(uuid4()) is None
