from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.eval_item import NewEvalItem, TestType
from shared.domain.eval_result import NewEvalResult
from shared.domain.eval_test_set import NewEvalTestSet
from shared.domain.project import NewProject
from shared.domain.question import NewQuestion, QuestionCategory, QuestionType
from shared.repositories.eval_items import EvalItemRepository
from shared.repositories.eval_results import EvalResultRepository
from shared.repositories.eval_test_sets import EvalTestSetRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.questions import QuestionRepository


async def _seed(conn: AsyncConnection):
    q = await QuestionRepository(conn).add(
        NewQuestion(
            question_category=QuestionCategory.CALCULATOR,
            question_type=QuestionType.LOOKUP,
            question_text="?",
        )
    )
    p = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-RES-001",
            project_name="P",
            vergabe_stelle="VS",
            project_location="X",
        )
    )
    item = await EvalItemRepository(conn).add(
        NewEvalItem(
            question_uuid=q.question_uuid,
            project_uuid=p.project_uuid,
            test_type=TestType.CONTEXT_RETRIEVAL,
            expected_result=["LV"],
        )
    )
    test_set = await EvalTestSetRepository(conn).add(NewEvalTestSet(name="V1"))
    return item, test_set


async def test_upsert_inserts_when_new(conn: AsyncConnection) -> None:
    item, test_set = await _seed(conn)
    repo = EvalResultRepository(conn)
    result = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set.test_set_uuid,
            actual_result=["LV"],
            passed=True,
            metrics={"context_recall": 1.0},
        )
    )
    assert result.eval_result_uuid is not None
    assert result.passed is True
    assert result.metrics == {"context_recall": 1.0}


async def test_upsert_overwrites_on_rerun(conn: AsyncConnection) -> None:
    item, test_set = await _seed(conn)
    repo = EvalResultRepository(conn)
    first = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set.test_set_uuid,
            actual_result=["LV"],
            passed=False,
            metrics={"context_recall": 0.0},
        )
    )
    # Sleep briefly so the post-rerun ran_at is strictly greater.
    await asyncio.sleep(0.01)
    second = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set.test_set_uuid,
            actual_result=["LV", "ZTV"],
            passed=True,
            metrics={"context_recall": 1.0},
        )
    )

    assert second.eval_result_uuid == first.eval_result_uuid
    assert second.passed is True
    assert second.actual_result == ["LV", "ZTV"]
    assert second.metrics == {"context_recall": 1.0}
    assert second.ran_at >= first.ran_at

    listed = await repo.list_by_test_set(test_set.test_set_uuid)
    assert len(listed) == 1


async def test_different_test_sets_get_separate_rows(conn: AsyncConnection) -> None:
    item, test_set_a = await _seed(conn)
    test_set_b = await EvalTestSetRepository(conn).add(NewEvalTestSet(name="V2"))
    repo = EvalResultRepository(conn)
    a = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set_a.test_set_uuid,
            passed=True,
        )
    )
    b = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set_b.test_set_uuid,
            passed=False,
        )
    )
    assert a.eval_result_uuid != b.eval_result_uuid


async def test_deleting_eval_item_cascades(conn: AsyncConnection) -> None:
    item, test_set = await _seed(conn)
    repo = EvalResultRepository(conn)
    result = await repo.upsert(
        NewEvalResult(
            eval_item_uuid=item.eval_item_uuid,
            test_set_uuid=test_set.test_set_uuid,
            passed=True,
        )
    )
    await EvalItemRepository(conn).delete(item.eval_item_uuid)
    assert await repo.get(result.eval_result_uuid) is None
