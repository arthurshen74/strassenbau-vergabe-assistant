from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.domain.eval_item import AnswerType, NewEvalItem, TestType


def _base(**overrides):
    base = dict(
        question_uuid=uuid4(),
        project_uuid=uuid4(),
        test_type=TestType.CONTEXT_RETRIEVAL,
        expected_result=["Baubeschreibung", "ZTV"],
    )
    base.update(overrides)
    return base


def test_context_retrieval_with_doc_list_is_valid() -> None:
    NewEvalItem(**_base())


def test_answer_correctness_numerical_is_valid() -> None:
    NewEvalItem(
        **_base(
            test_type=TestType.ANSWER_CORRECTNESS,
            answer_type=AnswerType.NUMERICAL,
            expected_result=12.5,
            numerical_tolerance=0.01,
        )
    )


def test_answer_correctness_factual_with_alternatives_is_valid() -> None:
    NewEvalItem(
        **_base(
            test_type=TestType.ANSWER_CORRECTNESS,
            answer_type=AnswerType.FACTUAL,
            expected_result="Asphaltbeton",
            acceptable_alternatives=["AC", "Tragschicht aus AC"],
        )
    )


def test_ragas_with_null_expected_result_is_valid() -> None:
    NewEvalItem(**_base(test_type=TestType.RAGAS, expected_result=None))


def test_answer_correctness_without_answer_type_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(
            **_base(
                test_type=TestType.ANSWER_CORRECTNESS,
                expected_result=12.5,
            )
        )


def test_answer_correctness_without_expected_result_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(
            **_base(
                test_type=TestType.ANSWER_CORRECTNESS,
                answer_type=AnswerType.NUMERICAL,
                expected_result=None,
                numerical_tolerance=0.01,
            )
        )


def test_context_retrieval_with_answer_type_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(
            **_base(
                test_type=TestType.CONTEXT_RETRIEVAL,
                answer_type=AnswerType.NUMERICAL,
            )
        )


def test_context_retrieval_without_expected_result_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(**_base(expected_result=None))


def test_ragas_with_expected_result_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(**_base(test_type=TestType.RAGAS, expected_result=["X"]))


def test_numerical_tolerance_without_numerical_answer_type_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(
            **_base(
                test_type=TestType.ANSWER_CORRECTNESS,
                answer_type=AnswerType.FACTUAL,
                expected_result="Asphaltbeton",
                numerical_tolerance=0.01,
            )
        )


def test_acceptable_alternatives_without_factual_answer_type_raises() -> None:
    with pytest.raises(ValidationError):
        NewEvalItem(
            **_base(
                test_type=TestType.ANSWER_CORRECTNESS,
                answer_type=AnswerType.NUMERICAL,
                expected_result=12.5,
                numerical_tolerance=0.01,
                acceptable_alternatives=["nope"],
            )
        )
