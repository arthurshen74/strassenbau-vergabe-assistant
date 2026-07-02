from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_leistungen = lifecycle_tabelle(
    "katalog_leistungen",
    "code",
    Column("name", Text, nullable=False),
    Column("beschreibung", Text, nullable=True),
    Column("standard_kennung", Text, nullable=True),
    Column("einheit", Text, nullable=True),
)
