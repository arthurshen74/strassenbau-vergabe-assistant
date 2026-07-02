from __future__ import annotations

from sqlalchemy import Column, Numeric, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_lieferanten = lifecycle_tabelle(
    "katalog_lieferanten",
    "code",
    Column("name", Text, nullable=False),
    Column("standort", Text, nullable=True),
    Column("breitengrad", Numeric, nullable=True),
    Column("laengengrad", Numeric, nullable=True),
)
