"""Junction: the ordered Vorgänge of one *version row* of a Bauverfahren.

Rows belong to a specific Bauverfahren version (by `zeile_uuid`) and are rewritten when the
Bauverfahren is superseded — hence the FK to `katalog_bauverfahren` with ON DELETE CASCADE.
`vorgang_code` references a Vorgang by code (version-independent); it gets no DB-level FK.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

katalog_bauverfahren_vorgaenge = Table(
    "katalog_bauverfahren_vorgaenge",
    metadata,
    Column(
        "zeile_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "bauverfahren_uuid",
        UUID(as_uuid=True),
        ForeignKey("katalog_bauverfahren.zeile_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("reihenfolge", Integer, nullable=False),
    Column("vorgang_code", Text, nullable=False),
    UniqueConstraint("bauverfahren_uuid", "reihenfolge"),
)
