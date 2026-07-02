"""Supplier price history (immutable rows). References Lieferant and Baustoff by code
(version-independent, so superseding a Lieferant does not orphan its price history). Price
validity (`gueltig_ab`/`gueltig_bis`) is domain time — a price correction inserts a new row,
never updates. Codes get no DB-level FK; integrity is enforced by the bundle validator.
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Numeric, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

katalog_lieferanten_preise = Table(
    "katalog_lieferanten_preise",
    metadata,
    Column(
        "zeile_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("lieferant_code", Text, nullable=False, index=True),
    Column("baustoff_code", Text, nullable=False),
    Column("preis_eur_pro_t", Numeric, nullable=False),
    Column("gueltig_ab", Date, nullable=False),
    Column("gueltig_bis", Date, nullable=True),
    Column(
        "erstellt_am",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
