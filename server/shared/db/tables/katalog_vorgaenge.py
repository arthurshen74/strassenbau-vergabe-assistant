from __future__ import annotations

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSON

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# JSON (not JSONB): the Kostenart order inside `rechnung.kosten` drives the Nachweis
# cost-line order, and jsonb reorders object keys — `json` preserves them for a
# byte-identical reload. Cross-entity code references (ausfuehrungsart_code,
# betriebsart_code) get no DB-level FK — codes are not unique across versions;
# referential integrity is enforced by the bundle validator.
katalog_vorgaenge = lifecycle_tabelle(
    "katalog_vorgaenge",
    "code",
    Column("name", Text, nullable=False),
    Column("ausfuehrungsart_code", Text, nullable=True),
    Column("betriebsart_code", Text, nullable=True),
    Column("leistung_instanz", Text, nullable=True),
    Column("kosten_bindung", JSON, nullable=False),
    Column("rechnung", JSON, nullable=False),
)
