"""The global catalog version — a single-row table (`katalog_stand`).

One row (`id = 1`) holds the catalog's monotonic `version` (bumped on every bundle
ACTIVATION, the number stamped onto calculations for provenance and compared for
reloads) plus the audit display: `aktualisiert_am`/`benutzer`, the last catalog write of
ANY kind (draft save, activate, discard, seed). `stand_beruehren` upserts it in the same
UoW as the write. A plain `create_all` table (new tables need no SQL migration).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, Table, Text, func

from shared.db.metadata import metadata

# Column names — one source of truth referenced by the repository and the seed.
SPALTE_ID = "id"
SPALTE_VERSION = "version"
SPALTE_AKTUALISIERT_AM = "aktualisiert_am"
SPALTE_BENUTZER = "benutzer"

# The singleton row's primary key.
STAND_ID = 1

katalog_stand = Table(
    "katalog_stand",
    metadata,
    Column(SPALTE_ID, Integer, primary_key=True, autoincrement=False),  # always 1
    Column(SPALTE_VERSION, Integer, nullable=False),  # monotonic; +1 per activation
    Column(
        SPALTE_AKTUALISIERT_AM,
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(SPALTE_BENUTZER, Text, nullable=True),  # who performed the last write
)
