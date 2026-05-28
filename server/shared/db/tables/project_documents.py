from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    Uuid,
    func,
    text,
)

from shared.db.metadata import metadata

project_documents = Table(
    "project_documents",
    metadata,
    Column(
        "project_document_uuid",
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
    Column("document_filename", Text, nullable=False),
    Column(
        "document_type_uuid",
        Uuid(as_uuid=True),
        ForeignKey("project_document_types.document_type_uuid"),
        nullable=False,
        index=True,
    ),
    Column("document_description", Text, nullable=True),
    Column("number_of_pages", Integer, nullable=True),
    Column(
        "ingested_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
