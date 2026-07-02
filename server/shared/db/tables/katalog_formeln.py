from __future__ import annotations

from sqlalchemy import Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# Natural key is `name` (Formeln are identified by name, not code).
katalog_formeln = lifecycle_tabelle(
    "katalog_formeln",
    "name",
    Column("ergebnis_variable", Text, nullable=False),
    Column("ausdruck", Text, nullable=False),
    Column("einheit", Text, nullable=True),
)
