from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_bauverfahren = lifecycle_tabelle(
    "katalog_bauverfahren",
    "code",
    Column("name", Text, nullable=False),
)
