from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Table,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from shared.db.metadata import metadata

eval_items = Table(
    "eval_items",
    metadata,
    Column(
        "eval_item_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "question_uuid",
        Uuid(as_uuid=True),
        ForeignKey("questions.question_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "project_uuid",
        Uuid(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("test_type", Text, nullable=False),
    Column("answer_type", Text, nullable=True),
    Column("numerical_tolerance", Double, nullable=True),
    Column("acceptable_alternatives", JSONB, nullable=True),
    Column("expected_result", JSONB, nullable=True),
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
        "test_type IN ('context_retrieval', 'answer_correctness', 'ragas')",
        name="test_type",
    ),
    CheckConstraint(
        "answer_type IS NULL OR answer_type IN "
        "('numerical', 'factual', 'yes_no', 'list')",
        name="answer_type",
    ),
)
