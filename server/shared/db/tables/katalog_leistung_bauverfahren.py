from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# Natural key is `leistung_code`; `bauverfahren_codes` is an ordered array (first entry = default) —
# JSON preserves that order on reload.
katalog_leistung_bauverfahren = lifecycle_tabelle(
    "katalog_leistung_bauverfahren",
    "leistung_code",
    Column("bauverfahren_codes", JSON, nullable=False),
)
