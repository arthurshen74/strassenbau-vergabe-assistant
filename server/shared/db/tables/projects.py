from __future__ import annotations

from sqlalchemy import Column, DateTime, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

# Only project_name is required: a project is created from its tender ZIP before the
# other header fields are known, and those are filled in after ingestion (or by hand).
projects = Table(
    "projects",
    metadata,
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_name", Text, nullable=False),  # Maßnahme
    Column("massnahmenummer", Text, nullable=True),
    Column("vergabe_id", Text, nullable=True),  # Vergabenummer
    Column("bauleistung", Text, nullable=True),
    Column("vergabestelle", Text, nullable=True),
    Column("location", Text, nullable=True),  # Baustelle
    Column("project_description", Text, nullable=True),
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
