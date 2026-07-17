"""Domain models for RAG reference questions (the retrieval/answer gold set).

One RagGroundTruth is a curated question with the expert's gold answer and the
Fundstellen (document + page) the answer comes from. Refs drive deterministic retrieval
metrics; the answer drives answer grading. See shared.services.rag_ground_truth.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import RagQuestionCategory, RagQuestionType


class RagRef(BaseModel):
    """One Fundstelle: the document and page where the answer is found."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    page: int = Field(ge=1)


class RagGroundTruthUpsert(BaseModel):
    """Create/edit body: the curated content. Scope and audit fields come from the
    route."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    gold_answer: str = Field(min_length=1)
    refs: list[RagRef] = Field(default_factory=list)
    question_type: RagQuestionType
    category: RagQuestionCategory


class NewRagGroundTruth(RagGroundTruthUpsert):
    """Insert model. PK and timestamps assigned by the DB."""

    project_uuid: UUID
    created_by_user_id: UUID


class RagGroundTruth(NewRagGroundTruth):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    rag_ground_truth_uuid: UUID
    created_at: datetime
    updated_at: datetime


class RagGroundTruthRead(RagGroundTruth):
    """Row plus the curation flag: a question without refs counts only toward answer
    grading, not retrieval metrics."""

    refs_missing: bool = False
