from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, PrimaryKeyConstraint, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

form_fields = Table(
    "form_fields",
    metadata,
    Column(
        "document_uuid",
        UUID(as_uuid=True),
        ForeignKey("documents.document_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    # Reading order within the document.
    Column("field_order", Integer, nullable=False),
    # XFA subform name or "Seite n" (AcroForm).
    Column("section", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("label", Text, nullable=True),
    Column("value", Text, nullable=False),
    Column("page", Integer, nullable=False),
    PrimaryKeyConstraint("document_uuid", "field_order"),
)
