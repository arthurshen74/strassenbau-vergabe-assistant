from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

ingest_job_events = Table(
    "ingest_job_events",
    metadata,
    Column(
        "job_event_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "job_uuid",
        UUID(as_uuid=True),
        ForeignKey("ingest_jobs.job_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("event", Text, nullable=False),
    Column("pipeline_phase", Text, nullable=True),
    Column("message", Text, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
