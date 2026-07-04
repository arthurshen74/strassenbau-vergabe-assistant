from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Table, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

# Per-item drill-down of a finished eval run: one row per graded position/fixture/question.
# payload is the grader's result dict (PositionResult / ChatFixtureResult shape per kind).
eval_results = Table(
    "eval_results",
    metadata,
    Column(
        "result_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "eval_run_uuid",
        UUID(as_uuid=True),
        ForeignKey("eval_runs.eval_run_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("item_id", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
