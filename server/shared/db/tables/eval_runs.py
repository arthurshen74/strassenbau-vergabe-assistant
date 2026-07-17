from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata
from shared.models.enums import EvalRunKind, EvalRunStatus

_KINDS_SQL = ", ".join(f"'{k.value}'" for k in EvalRunKind)
_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in EvalRunStatus)

# One eval run: which grader (kind), its scope/params, the queue state (same
# competing-consumer lease mechanics as ingest_jobs), and on completion the summary
# metrics keyed to the prompt versions the run exercised. Per-item results live in
# eval_results; progress in eval_run_events.
eval_runs = Table(
    "eval_runs",
    metadata,
    Column(
        "eval_run_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("kind", Text, nullable=False),
    # Scope for project-bound kinds (calculator_gold, rag_*); chat_values runs without
    # one.
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=True,
        index=True,
    ),
    # Kind-specific knobs (abs_tol, limit, dataset ...).
    Column("params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column(
        "status",
        Text,
        nullable=False,
        server_default=text(f"'{EvalRunStatus.QUEUED.value}'"),
    ),
    # Lease for crash recovery: claim_next stamps locked_at/locked_by and every progress
    # event refreshes locked_at; an expired lease is reclaimable. attempts bounds
    # auto-retries.
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("locked_by", Text, nullable=True),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("error", Text, nullable=True),
    Column("summary", JSONB, nullable=True),
    Column("prompt_versions", JSONB, nullable=True),
    # Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins
    # to auth).
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
    CheckConstraint(f"kind IN ({_KINDS_SQL})", name="kind_valid"),
    CheckConstraint(f"status IN ({_STATUSES_SQL})", name="status_valid"),
    Index("ix_eval_runs_status_locked_at", "status", "locked_at"),
)
