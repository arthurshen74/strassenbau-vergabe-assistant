from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_ausfuehrungsarten = lifecycle_tabelle(
    "katalog_ausfuehrungsarten",
    "code",
    Column("name", Text, nullable=False),
    Column("geraetebezug", Text, nullable=True),
)
