from __future__ import annotations

from sqlalchemy import (
    Boolean,
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
from shared.models.enums import IngestStatus

_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in IngestStatus)

# One Projektinfo extraction per row: runs the project-info RAG queries once the
# project's ingest jobs have settled and writes the found values into `projects`. Same
# competing-consumer lease mechanics as ingest_jobs.
project_info_jobs = Table(
    "project_info_jobs",
    metadata,
    Column(
        "job_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Language of the RAG query versions to run, fixed at enqueue.
    Column("language", Text, nullable=False),
    # True writes every found value; false only fills NULL columns.
    Column("overwrite", Boolean, nullable=False, server_default=text("false")),
    Column(
        "status",
        Text,
        nullable=False,
        server_default=text(f"'{IngestStatus.QUEUED.value}'"),
    ),
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("locked_by", Text, nullable=True),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("error", Text, nullable=True),
    # Per query_key: {gefunden, wert, konfidenz, beleg, query_version, error}.
    Column("result", JSONB, nullable=True),
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
    CheckConstraint(f"status IN ({_STATUSES_SQL})", name="status_valid"),
    Index("ix_project_info_jobs_status_locked_at", "status", "locked_at"),
)
