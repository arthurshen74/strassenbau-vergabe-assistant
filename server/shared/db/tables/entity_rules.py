"""EntityRuler rules: one spaCy pattern per row, live-editable and DB-backed.

`pattern` is the raw spaCy token-pattern DSL (a phrase string or a list of
token-attribute objects) stored as JSONB — spaCy is the validator at the write
boundary, so it is not modeled further (design D1). `pattern_id` is spaCy's
optional pattern grouping id (the fixture's `id`), carried onto every matched
entity for provenance; it is free text, not an enum (design D2).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

entity_rules = Table(
    "entity_rules",
    metadata,
    Column(
        "entity_rule_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("label", Text, nullable=False, index=True),
    Column("pattern", JSONB, nullable=False),
    Column("pattern_id", Text, nullable=True),
    Column("enabled", Boolean, nullable=False, server_default=text("true")),
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
)
