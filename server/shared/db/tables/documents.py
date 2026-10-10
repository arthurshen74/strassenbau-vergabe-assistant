from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import DocumentType

# The CHECK predicate is built from the enum so a rename can't drift.
_DOCUMENT_TYPES_SQL = ", ".join(f"'{t.value}'" for t in DocumentType)

documents = Table(
    "documents",
    metadata,
    Column(
        "document_uuid",
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
    Column("document_type", Text, nullable=False),
    Column("file_name", Text, nullable=False),
    Column("document_description", Text, nullable=True),
    Column("number_of_pages", Integer, nullable=False),
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
        f"document_type IN ({_DOCUMENT_TYPES_SQL})", name="document_type_valid"
    ),
)

# Order for listing LV documents and the rows across them. Documents uploaded in one
# request share created_at (transaction time), so the uuid breaks the tie and keeps
# each document's rows together.
LV_DOCUMENT_ORDER = (documents.c.created_at, documents.c.document_uuid)
