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

ingest_job_events = Table(
    "ingest_job_events",
    metadata,
    Column(
        "ingest_job_event_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "ingest_job_uuid",
        Uuid(as_uuid=True),
        ForeignKey("ingest_jobs.ingest_job_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("event", Text, nullable=False),
    Column("phase", Text, nullable=True),
    Column("message", Text, nullable=True),
    Column(
        "ts",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "event IN ('ingest_started', 'ingest_progress', "
        "'ingest_completed', 'ingest_error')",
        name="event",
    ),
)
