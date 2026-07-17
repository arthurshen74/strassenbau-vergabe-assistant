"""ner_flags: persisted NER mispredictions plus their one-shot LLM error analysis.

Each row is a point-in-time record — it snapshots the analyzed source text, the
flag-time entity list, and the model/prompt/ruleset provenance, so it stays
interpretable even after the ruleset or models change. Source linkage (LV item /
document) is nullable provenance, not the data: ad-hoc text flags stand alone.
"""

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
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata
from shared.models.enums import NerFailureCategory, NerFlagKind, NerFlagStatus

_KINDS_SQL = ", ".join(f"'{k.value}'" for k in NerFlagKind)
_CATEGORIES_SQL = ", ".join(f"'{c.value}'" for c in NerFailureCategory)
_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in NerFlagStatus)

ner_flags = Table(
    "ner_flags",
    metadata,
    Column(
        "ner_flag_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("kind", Text, nullable=False),
    Column("span_text", Text, nullable=False),
    Column("span_start", Integer, nullable=False),
    Column("span_end", Integer, nullable=False),
    Column("sentence_text", Text, nullable=False),
    Column("label", Text, nullable=False),
    Column("expected_label", Text, nullable=True),
    Column("user_comment", Text, nullable=False),
    Column("source_text", Text, nullable=False),
    Column("entity_snapshot", JSONB, nullable=False),
    # Source linkage is provenance; SET NULL so a flag outlives its LV item / document.
    Column(
        "lv_item_uuid",
        UUID(as_uuid=True),
        ForeignKey("lv_items.lv_item_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column(
        "document_uuid",
        UUID(as_uuid=True),
        ForeignKey("documents.document_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    # LLM error-analysis output (null until analysis succeeds).
    Column("category", Text, nullable=True),
    Column("category_override", Text, nullable=True),
    Column("llm_analysis", Text, nullable=True),
    Column("suggested_rule", JSONB, nullable=True),
    # Analysis provenance.
    Column("llm_model", Text, nullable=True),
    Column("prompt_version", Integer, nullable=True),
    Column("spacy_model_version", Text, nullable=True),
    Column("analyzed_at", DateTime(timezone=True), nullable=True),
    Column("status", Text, nullable=False, server_default=NerFlagStatus.OPEN.value),
    Column("resolved_note", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    CheckConstraint(f"kind IN ({_KINDS_SQL})", name="kind_valid"),
    CheckConstraint(
        f"category IS NULL OR category IN ({_CATEGORIES_SQL})", name="category_valid"
    ),
    CheckConstraint(
        f"category_override IS NULL OR category_override IN ({_CATEGORIES_SQL})",
        name="category_override_valid",
    ),
    CheckConstraint(f"status IN ({_STATUSES_SQL})", name="status_valid"),
)
