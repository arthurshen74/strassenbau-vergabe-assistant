from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_betriebsarten = lifecycle_tabelle(
    "katalog_betriebsarten",
    "code",
    Column("bezeichnung", Text, nullable=False),
    Column("kategorie_code", Text, nullable=False),
    Column("einheit", Text, nullable=True),
    Column("beschreibung", Text, nullable=True),
)
