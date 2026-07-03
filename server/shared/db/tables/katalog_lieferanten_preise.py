"""Supplier price history (immutable value rows). References Lieferant and Baustoff by code
(version-independent, so superseding a Lieferant does not orphan its price history). Price
validity (`gueltig_ab`/`gueltig_bis`) is domain time — a price correction inserts a new row,
never updates. Codes get no DB-level FK; integrity is enforced by the bundle validator.

Phase 2 adds a lifecycle `status` (+ `bundle_uuid`/`benutzer`) so a price rides the
draft→confirm flow (D5): the VALUE stays immutable, the status only tracks entwurf|aktiv|
archiviert. The columns are added by `sql/11` on an existing DB (ALTER; create_all never alters).
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
    Column("status", Text, nullable=False),  # KatalogStatus value (entwurf|aktiv|archiviert)
    Column("bundle_uuid", UUID(as_uuid=True), nullable=True),  # the draft bundle it rode in on
    Column("benutzer", Text, nullable=True),  # who proposed it
    Column(
        "erstellt_am",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
