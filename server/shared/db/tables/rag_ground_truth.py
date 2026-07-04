from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata
from shared.models.enums import RagQuestionCategory, RagQuestionType

_QUESTION_TYPES_SQL = ", ".join(f"'{t.value}'" for t in RagQuestionType)
_CATEGORIES_SQL = ", ".join(f"'{c.value}'" for c in RagQuestionCategory)

# One curated RAG reference question for a project: the question, the expert's gold answer, and
# the Fundstellen (document + page) the answer comes from. The refs drive deterministic retrieval
# metrics (recall@k, MRR); the answer drives answer grading. A row without refs is legal — it
# counts only toward answer grading.
rag_ground_truth = Table(
    "rag_ground_truth",
    metadata,
    Column(
        "rag_ground_truth_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("question", Text, nullable=False),
    Column("gold_answer", Text, nullable=False),
    # list of {document_uuid, page}: where the answer is found (page-level citations).
    Column("refs", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("question_type", Text, nullable=False),
    Column("category", Text, nullable=False),
    # Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    CheckConstraint(
        f"question_type IN ({_QUESTION_TYPES_SQL})",
        name="question_type_valid",
    ),
    CheckConstraint(
        f"category IN ({_CATEGORIES_SQL})",
        name="category_valid",
    ),
)
