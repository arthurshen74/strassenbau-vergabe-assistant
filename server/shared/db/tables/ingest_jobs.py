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
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import IngestStatus

_INGEST_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in IngestStatus)

ingest_jobs = Table(
    "ingest_jobs",
    metadata,
    Column(
        "job_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "document_uuid",
        UUID(as_uuid=True),
        ForeignKey("documents.document_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "status",
        Text,
        nullable=False,
        server_default=text(f"'{IngestStatus.QUEUED.value}'"),
    ),
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
    # Lease for crash recovery: claim_next stamps locked_at/locked_by and the worker's activity
    # flush keeps locked_at fresh; an expired lease is reclaimable. attempts bounds auto-retries.
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("locked_by", Text, nullable=True),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(f"status IN ({_INGEST_STATUSES_SQL})", name="status_valid"),
    Index("ix_ingest_jobs_status_locked_at", "status", "locked_at"),
)
