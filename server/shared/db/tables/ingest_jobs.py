from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    Uuid,
    func,
    text,
)

from shared.db.metadata import metadata

ingest_jobs = Table(
    "ingest_jobs",
    metadata,
    Column(
        "ingest_job_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "project_uuid",
        Uuid(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "project_document_uuid",
        Uuid(as_uuid=True),
        ForeignKey("project_documents.project_document_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "status",
        Text,
        nullable=False,
        server_default=text("'queued'"),
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
    CheckConstraint(
        "status IN ('queued', 'running', 'done', 'failed')",
        name="status",
    ),
)
