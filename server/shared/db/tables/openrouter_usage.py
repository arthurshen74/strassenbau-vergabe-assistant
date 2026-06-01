from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import UsageOperation

# CHECK predicate is built from the enum so a rename can't drift.
_USAGE_OPERATIONS_SQL = ", ".join(f"'{o.value}'" for o in UsageOperation)

openrouter_usage = Table(
    "openrouter_usage",
    metadata,
    Column(
        "usage_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("operation", Text, nullable=False),
    Column("model", Text, nullable=False),
    # Every metric is nullable: each is optional in at least one endpoint's usage schema
    # (rerank has no prompt/completion tokens; embeddings/rerank may omit cost).
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("total_tokens", Integer, nullable=True),
    Column("cost", Numeric(18, 8), nullable=True),
    Column("cached_tokens", Integer, nullable=True),
    Column("reasoning_tokens", Integer, nullable=True),
    Column("search_units", Integer, nullable=True),
    # Attribution: SET NULL so cost history outlives a deleted project/job.
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column(
        "ingest_job_uuid",
        UUID(as_uuid=True),
        ForeignKey("ingest_jobs.job_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column("request_id", Text, nullable=True),
    # Plain columns (not a FK) so a usage row survives prompt-version churn.
    Column("chat_prompt_type", Text, nullable=True),
    Column("chat_prompt_version", Integer, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        f"operation IN ({_USAGE_OPERATIONS_SQL})", name="operation_valid"
    ),
)
