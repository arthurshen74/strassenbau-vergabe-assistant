from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

# Granular activity of a Projektinfo job, the counterpart of ingestion_activity_log:
# the worker's buffered flushes also bump project_info_jobs.locked_at, and the live
# console tails it. Pruned after settings.activity_retention_hours; no archive.
project_info_activity_log = Table(
    "project_info_activity_log",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "job_uuid",
        UUID(as_uuid=True),
        ForeignKey("project_info_jobs.job_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("worker_id", Text, nullable=False),
    Column("phase", Text, nullable=True),
    Column("message", Text, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Tail by (job, id) cursor for the UI terminal and the console's latest line.
    Index("ix_project_info_activity_job_id", "job_uuid", "id"),
)
