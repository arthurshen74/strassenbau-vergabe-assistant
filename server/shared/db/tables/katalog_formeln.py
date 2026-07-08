from __future__ import annotations

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSON

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# Natural key is `name` (Formeln are identified by name, not code). A row is a BASE formula:
# expression over declared parameters (JSON list of {name, einheit, beschreibung, standard} —
# JSON not JSONB, parameter order is the signature order) plus mandatory prose.
katalog_formeln = lifecycle_tabelle(
    "katalog_formeln",
    "name",
    Column("ausdruck", Text, nullable=False),
    Column("einheit", Text, nullable=True),
    Column("beschreibung", Text, nullable=True),
    Column("parameter", JSON, nullable=False),
)
