from __future__ import annotations

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSON

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

# `gruppe` (VariablenGruppe: stammdaten | kontext | formel) preserves the three fixture sources so
# the provider can rebuild STAMMDATEN/KONTEXT/FORMEL_VARIABLEN and their KATALOG merge exactly.
# One name may appear in two gruppen (a stammdaten constant deliberately shadowed by a formula), so
# `gruppe` is part of the natural key: version + active uniqueness are per (name, gruppe).
# JSON (not JSONB), uniform with the other katalog payload columns: jsonb reorders object keys on
# write (the load-bearing case is katalog_vorgaenge.kostenvariablen — Nachweis cost-line order).
katalog_variablen = lifecycle_tabelle(
    "katalog_variablen",
    "name",
    Column("gruppe", Text, nullable=False),
    Column("bezeichnung", Text, nullable=False),
    Column("beschreibung", Text, nullable=True),
    Column("einheit", Text, nullable=True),
    Column("datentyp", Text, nullable=False),
    Column("llm_kontext", Text, nullable=True),
    Column("aufloesung", JSON, nullable=False),
    diskriminator="gruppe",
)
