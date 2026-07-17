from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

# Cold archive for ingestion_activity_log: the worker moves aged-out rows here so the
# active table stays small while the full per-document history is preserved (read as
# active UNION archive). id mirrors the original active-table id (plain bigint, not
# identity) so it survives the move and orders the union.
ingestion_activity_log_archive = Table(
    "ingestion_activity_log_archive",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=False),
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
    Column("ts", DateTime(timezone=True), nullable=False),
    # Read path: a document's full history, oldest first.
    Index("ix_activity_archive_document_id", "document_uuid", "id"),
)
