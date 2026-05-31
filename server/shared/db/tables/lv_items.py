from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from shared.db.metadata import metadata

lv_items = Table(
    "lv_items",
    metadata,
    Column(
        "lv_item_uuid",
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
    Column("oz", Text, nullable=False),
    Column("kurztext", Text, nullable=False),
    Column("langtext", Text, nullable=False),
    Column("langtext_resolved", Text, nullable=True),
    Column("menge", Numeric(12, 4), nullable=False),
    Column("einheit", Text, nullable=False),
    Column("positionstyp", Text, nullable=True),
    Column("level", Integer, nullable=True),
    Column("stl_nr", Text, nullable=True),
    Column("hinweis", Text, nullable=True),
    Column("linked_oz", Text, nullable=True),
    Column("prev_oz", Text, nullable=True),
    Column("next_oz", Text, nullable=True),
    Column("parent_oz", Text, nullable=True),
    Column(
        "source_lines",
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    ),
    Column(
        "last_ingestion",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    UniqueConstraint("document_uuid", "oz"),
)
