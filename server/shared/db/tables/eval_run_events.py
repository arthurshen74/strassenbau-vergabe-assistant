from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

# Append-only progress log of an eval run (one row per emitted message), the live feed
# the UI polls while a run executes.
eval_run_events = Table(
    "eval_run_events",
    metadata,
    Column(
        "event_uuid",
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
    Column("message", Text, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
