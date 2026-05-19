from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QuestionCategory(StrEnum):
    CALCULATOR = "calculator"
    BAULEITER = "bauleiter"


class QuestionType(StrEnum):
    LOOKUP = "lookup"
    AGGREGATION = "aggregation"
    CROSS_DOC_CONDITIONAL = "cross_doc_conditional"
    CONSTRAINT_SURFACING = "constraint_surfacing"
    MULTI_HOP = "multi_hop"


class NewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_category: QuestionCategory
    question_type: QuestionType
    question_text: str


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_uuid: UUID
    question_category: QuestionCategory
    question_type: QuestionType
    question_text: str
    created_at: datetime
    updated_at: datetime
