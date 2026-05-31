from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from shared.db.metadata import metadata

source_lines = Table(
    "source_lines",
    metadata,
    Column(
        "source_line_uuid",
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
    Column("line_id", Integer, nullable=False),
    Column("page", Integer, nullable=False),
    # (x0, y0, x1, y1) from pdfplumber; fixed length enforced by the domain model.
    Column("bbox", ARRAY(Float), nullable=False),
    Column("line_text", Text, nullable=False),
    UniqueConstraint("document_uuid", "line_id"),
)
