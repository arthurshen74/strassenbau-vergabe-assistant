from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)

from shared.db.metadata import metadata

document_thumbnails = Table(
    "document_thumbnails",
    metadata,
    Column(
        "thumbnail_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "project_document_uuid",
        Uuid(as_uuid=True),
        ForeignKey("project_documents.project_document_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("page_number", Integer, nullable=False),
    Column("object_key", Text, nullable=False),
    Column("bucket", Text, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("content_type", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "project_document_uuid",
        "page_number",
        name="uq_document_thumbnails_project_document_uuid",
    ),
)
