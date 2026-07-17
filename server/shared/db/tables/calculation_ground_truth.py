from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

# The expert-confirmed answer for one LV position's EKT calculation, captured at Gate B
# when the
# Kalkulator marks the reviewed state as ground truth. One row per (project, position):
# re-saving a position upserts it (latest wins); the variable_corrections log preserves
# the change history.
calculation_ground_truth = Table(
    "calculation_ground_truth",
    metadata,
    Column(
        "ground_truth_uuid",
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
    Column(
        "lv_item_uuid",
        UUID(as_uuid=True),
        ForeignKey("lv_items.lv_item_uuid", ondelete="CASCADE"),
        nullable=False,
    ),
    # The run this gold was captured from; SET NULL so the gold outlives a deleted
    # conversation.
    Column(
        "source_conversation_uuid",
        UUID(as_uuid=True),
        ForeignKey("conversations.conversation_uuid", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("oz", Text, nullable=True),
    Column("leistung_key", Text, nullable=False),
    Column("bauverfahren_key", Text, nullable=True),
    # name -> {wert, einheit, art, quelle, overridden}: the endorsed value for every
    # reviewed leaf.
    Column("gold_variables", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    # Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins
    # to auth).
    Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
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
    UniqueConstraint("project_uuid", "lv_item_uuid"),
)
