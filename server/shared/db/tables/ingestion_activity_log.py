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

# Granular per-job activity stream: the worker's liveness signal (its flushes also bump
# ingest_jobs.locked_at) and the feed for the live UI terminal. High-frequency and prunable,
# kept separate from the coarse ingest_job_events milestone stream that drives the status bar.
ingestion_activity_log = Table(
    "ingestion_activity_log",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "job_uuid",
        UUID(as_uuid=True),
        ForeignKey("ingest_jobs.job_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "document_uuid",
        UUID(as_uuid=True),
        ForeignKey("documents.document_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("worker_id", Text, nullable=False),
    Column("phase", Text, nullable=True),
    Column("message", Text, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Tail by (job, id) cursor for the UI terminal.
    Index("ix_activity_job_id", "job_uuid", "id"),
)
