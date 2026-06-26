from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import VariableCorrectionReason

# reason records why the Kalkulator overrode the proposal; the tag drives eval validity
# (see VariableCorrectionReason).
_CORRECTION_REASONS_SQL = ", ".join(f"'{r.value}'" for r in VariableCorrectionReason)

# Append-only log of every Gate B override: the model's proposal (value + provenance + confidence)
# vs the value the Kalkulator set, with an optional reason. This is error-analysis telemetry,
# captured on every override regardless of whether the run was also saved as ground truth.
variable_corrections = Table(
    "variable_corrections",
    metadata,
    Column(
        "correction_uuid",
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
    # SET NULL so the telemetry survives a position being removed on re-ingest.
    Column(
        "lv_item_uuid",
        UUID(as_uuid=True),
        ForeignKey("lv_items.lv_item_uuid", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("oz", Text, nullable=True),
    Column(
        "conversation_uuid",
        UUID(as_uuid=True),
        ForeignKey("conversations.conversation_uuid", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("leistung_key", Text, nullable=True),
    Column("bauverfahren_key", Text, nullable=True),
    Column("variable_name", Text, nullable=False, index=True),
    Column("proposed_wert", Text, nullable=True),
    Column("proposed_quelle", Text, nullable=True),
    Column("proposed_konfidenz", Text, nullable=True),
    Column("proposed_beleg", Text, nullable=True),
    Column("final_wert", Text, nullable=False),
    Column("reason", Text, nullable=True),
    Column("note", Text, nullable=True),
    # Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        f"reason IS NULL OR reason IN ({_CORRECTION_REASONS_SQL})",
        name="correction_reason_valid",
    ),
)
