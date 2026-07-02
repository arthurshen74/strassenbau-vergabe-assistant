from __future__ import annotations

from sqlalchemy import Column, Numeric, Text

from shared.db.tables.katalog_lifecycle import lifecycle_tabelle

katalog_baustoffe = lifecycle_tabelle(
    "katalog_baustoffe",
    "code",
    Column("name", Text, nullable=False),
    Column("rohdichte_t_pro_m3", Numeric, nullable=False),
    Column("verdichtungsfaktor", Numeric, nullable=False),
    Column("kategorie", Text, nullable=True),
    Column("koernung", Text, nullable=True),
    Column("einheit", Text, nullable=False),
    Column("basispreis_eur_pro_t", Numeric, nullable=True),
    Column("basispreis_eur", Numeric, nullable=True),
)
