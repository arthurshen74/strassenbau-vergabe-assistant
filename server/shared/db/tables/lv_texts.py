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
from shared.models.enums import LVTextKind, LVTextPlacement

# CHECK predicates are built from the enums so a rename can't drift.
_KINDS_SQL = ", ".join(f"'{k.value}'" for k in LVTextKind)
_PLACEMENTS_SQL = ", ".join(f"'{p.value}'" for p in LVTextPlacement)

lv_texts = Table(
    "lv_texts",
    metadata,
    Column(
        "lv_text_uuid",
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
    Column("kind", Text, nullable=False),
    Column("placement", Text, nullable=True),
    Column("parent_oz", Text, nullable=True),
    Column("index", Integer, nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("oz", Text, nullable=True),
    Column("heading", Text, nullable=True),
    Column("body", Text, nullable=False),
    Column(
        "last_ingestion",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    CheckConstraint(f"kind IN ({_KINDS_SQL})", name="lv_text_kind_valid"),
    CheckConstraint(
        f"placement IS NULL OR placement IN ({_PLACEMENTS_SQL})",
        name="lv_text_placement_valid",
    ),
)
