from __future__ import annotations

from sqlalchemy import Boolean, Column, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_globale_variablen = lifecycle_tabelle(
    "katalog_globale_variablen",
    "name",
    Column("bezeichnung", Text, nullable=False),
    Column("einheit", Text, nullable=True),
    Column("datentyp", Text, nullable=False),
    Column("ist_standort", Boolean, nullable=False),
    Column("erforderlich", Boolean, nullable=False),
    Column("ziel_variable", Text, nullable=True),
    Column("rag_prompt", Text, nullable=False),
)
