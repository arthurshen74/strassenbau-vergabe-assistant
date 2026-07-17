"""Per-variable version history (SCD-2) for project-scoped context globals.

One row per (project, variable, version). An override closes out the current row
(`gueltig_bis`, `ist_aktuell=false`) and inserts the next version; a version's
value/source are never altered. The partial unique index keeps exactly one current
(`ist_aktuell`) row per (project, variable).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

project_context_values = Table(
    "project_context_values",
    metadata,
    Column(
        "project_context_value_uuid",
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
    Column("variable_name", Text, nullable=False),  # e.g. "baustelle_location"
    Column("version", Integer, nullable=False),  # 1,2,3... per (project, variable)
    Column(
        "wert", Text, nullable=False
    ),  # user-facing value (address string or number)
    Column("breitengrad", Text, nullable=True),  # derived coords (location vars only)
    Column("laengengrad", Text, nullable=True),
    Column("quelle", Text, nullable=False),  # ContextQuelle: rag | hitl | routing
    Column("beleg", Text, nullable=True),  # literal evidence quote
    Column("quelle_referenz", JSONB, nullable=True),  # structured source provenance
    Column("konfidenz", Numeric, nullable=True),
    Column(
        "benutzer", Text, nullable=True
    ),  # HITL override user (denormalized for filter)
    Column(
        "status", Text, nullable=True
    ),  # location: aufgeloest|unsicher|fehlgeschlagen
    Column("ist_aktuell", Boolean, nullable=False, server_default=text("true")),
    Column(
        "gueltig_ab",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "gueltig_bis", DateTime(timezone=True), nullable=True
    ),  # set on supersede (SCD-2)
    Column(
        "erstellt_am",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint("project_uuid", "variable_name", "version"),
    Index(
        "uq_pcv_aktuell",
        "project_uuid",
        "variable_name",
        unique=True,
        postgresql_where=text("ist_aktuell"),
    ),  # exactly one current row per variable
)
