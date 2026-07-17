from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

# One row per document per layout-model version: the Docling layout inference output
# (list of LayoutRegion dicts) cached forever, since raw PDFs are immutable. A model
# upgrade writes a new row instead of invalidating; lookups key on (document, version).
document_layout_regions = Table(
    "document_layout_regions",
    metadata,
    Column(
        "document_uuid",
        UUID(as_uuid=True),
        ForeignKey("documents.document_uuid", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("model_version", Text, primary_key=True),
    Column("regions", JSONB, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
