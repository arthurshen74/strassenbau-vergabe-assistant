from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Table,
    Text,
    Uuid,
    func,
    text,
)

from shared.db.metadata import metadata

questions = Table(
    "questions",
    metadata,
    Column(
        "question_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("question_category", Text, nullable=False),
    Column("question_type", Text, nullable=False),
    Column("question_text", Text, nullable=False),
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
        "question_category IN ('calculator', 'bauleiter')",
        name="question_category",
    ),
    CheckConstraint(
        "question_type IN ('lookup', 'aggregation', 'cross_doc_conditional', "
        "'constraint_surfacing', 'multi_hop')",
        name="question_type",
    ),
)
