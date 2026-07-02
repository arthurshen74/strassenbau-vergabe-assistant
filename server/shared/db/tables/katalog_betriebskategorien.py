from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_betriebskategorien = lifecycle_tabelle(
    "katalog_betriebskategorien",
    "code",
    Column("bezeichnung", Text, nullable=False),
    Column("beschreibung", Text, nullable=True),
)
