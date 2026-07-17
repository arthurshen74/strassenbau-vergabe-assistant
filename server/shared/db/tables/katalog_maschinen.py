from __future__ import annotations

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSON

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# JSON (not JSONB) to preserve object-key order on reload (byte-identical property
# bags).
katalog_maschinen = lifecycle_tabelle(
    "katalog_maschinen",
    "code",
    Column("hersteller", Text, nullable=False),
    Column("modell", Text, nullable=False),
    Column("ausfuehrungsart_code", Text, nullable=False),
    Column("eigenschaften", JSON, nullable=False),
    Column("leistungsprofile", JSON, nullable=False),
)
