from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Table,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from shared.db.metadata import metadata

eval_results = Table(
    "eval_results",
    metadata,
    Column(
        "eval_result_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "eval_item_uuid",
        Uuid(as_uuid=True),
        ForeignKey("eval_items.eval_item_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "test_set_uuid",
        Uuid(as_uuid=True),
        ForeignKey("eval_test_sets.test_set_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "ran_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("actual_result", JSONB, nullable=True),
    Column("passed", Boolean, nullable=False),
    Column("metrics", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    UniqueConstraint(
        "eval_item_uuid",
        "test_set_uuid",
        name="uq_eval_results_eval_item_test_set",
    ),
)
