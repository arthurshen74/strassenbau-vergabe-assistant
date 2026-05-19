from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class TestType(StrEnum):
    __test__ = False  # silence pytest collection of "Test*" class names

    CONTEXT_RETRIEVAL = "context_retrieval"
    ANSWER_CORRECTNESS = "answer_correctness"
    RAGAS = "ragas"


class AnswerType(StrEnum):
    NUMERICAL = "numerical"
    FACTUAL = "factual"
    YES_NO = "yes_no"
    LIST = "list"


def _check_coherence(values: "EvalItemFields") -> "EvalItemFields":
    """Enforce EVALUATION.md §"EvalItem Structure" coherence rules."""
    if values.test_type == TestType.ANSWER_CORRECTNESS:
        if values.answer_type is None:
            raise ValueError(
                "answer_type is required when test_type='answer_correctness'"
            )
        if values.expected_result is None:
            raise ValueError(
                "expected_result is required when test_type='answer_correctness'"
            )
    else:
        if values.answer_type is not None:
            raise ValueError(
                "answer_type must be null unless test_type='answer_correctness'"
            )

    if values.test_type == TestType.RAGAS:
        if values.expected_result is not None:
            raise ValueError(
                "expected_result must be null when test_type='ragas'"
            )
    elif values.test_type == TestType.CONTEXT_RETRIEVAL:
        if values.expected_result is None:
            raise ValueError(
                "expected_result is required when test_type='context_retrieval'"
            )

    if values.numerical_tolerance is not None and values.answer_type != AnswerType.NUMERICAL:
        raise ValueError(
            "numerical_tolerance is only valid when answer_type='numerical'"
        )

    if (
        values.acceptable_alternatives is not None
        and values.answer_type != AnswerType.FACTUAL
    ):
        raise ValueError(
            "acceptable_alternatives is only valid when answer_type='factual'"
        )

    return values


class EvalItemFields(BaseModel):
    """Shared fields between NewEvalItem and EvalItem; coherence validated here."""

    model_config = ConfigDict(extra="forbid")

    question_uuid: UUID
    project_uuid: UUID
    test_type: TestType
    answer_type: AnswerType | None = None
    numerical_tolerance: float | None = None
    acceptable_alternatives: list[str] | None = None
    expected_result: Any | None = None

    @model_validator(mode="after")
    def _validate_coherence(self) -> "EvalItemFields":
        return _check_coherence(self)


class NewEvalItem(EvalItemFields):
    pass


class EvalItem(EvalItemFields):
    eval_item_uuid: UUID
    created_at: datetime
    updated_at: datetime
