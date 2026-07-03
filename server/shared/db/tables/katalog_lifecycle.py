"""Shared lifecycle scaffolding for the `katalog_*` tables.

Every lifecycle catalog table has the same shape: a `zeile_uuid` PK, a natural-key column
(`code`, or `name` for Formeln/Variablen), the entity's payload columns, and the seven
lifecycle columns below. Editing never mutates a row — a change inserts the next `version`
as `entwurf`; activation archives the current `aktiv` row and promotes the draft. The partial
unique index keeps exactly one `aktiv` row per natural key (same pattern as
`project_context_values`). `lifecycle_tabelle` assembles the whole table so the 13 near-identical
tables do not each re-declare the pattern.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.katalog import KatalogStatus

# Lifecycle column names — one source of truth referenced by the tables, the generic
# repository, the seed and the provider (never re-typed on either side of the contract).
SPALTE_ZEILE_UUID = "zeile_uuid"
SPALTE_VERSION = "version"
SPALTE_STATUS = "status"
SPALTE_BUNDLE_UUID = "bundle_uuid"
SPALTE_BENUTZER = "benutzer"
SPALTE_GUELTIG_AB = "gueltig_ab"
SPALTE_GUELTIG_BIS = "gueltig_bis"
SPALTE_ERSTELLT_AM = "erstellt_am"


def lifecycle_spalten() -> list[Column]:
    """Fresh lifecycle Column objects (SQLAlchemy columns are single-use, so build per call)."""
    return [
        Column(SPALTE_VERSION, Integer, nullable=False),  # 1,2,3… per natural key
        Column(SPALTE_STATUS, Text, nullable=False),  # KatalogStatus value
        Column(SPALTE_BUNDLE_UUID, UUID(as_uuid=True), nullable=True),  # rows written together
        Column(SPALTE_BENUTZER, Text, nullable=True),  # author ("seed" for fixtures)
        Column(
            SPALTE_GUELTIG_AB,
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(SPALTE_GUELTIG_BIS, DateTime(timezone=True), nullable=True),  # set on archive/discard
        Column(
            SPALTE_ERSTELLT_AM,
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    ]


def lifecycle_tabelle(
    name: str, schluessel: str, *payload: Column, diskriminator: str | None = None
) -> Table:
    """A `katalog_*` lifecycle table: `zeile_uuid` PK, the natural-key column, the payload
    columns, the lifecycle columns, `UNIQUE(<key>, version)` and the one-`aktiv`-per-key index.

    `diskriminator` extends the natural key with a second payload column (e.g. `gruppe`): version
    and active uniqueness become per (key, diskriminator), so the same key may appear once per
    discriminator value (a variable name shadowed across two gruppen)."""
    schluessel_spalten = [schluessel] if diskriminator is None else [schluessel, diskriminator]
    return Table(
        name,
        metadata,
        Column(
            SPALTE_ZEILE_UUID,
            UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
        Column(schluessel, Text, nullable=False),
        *payload,
        *lifecycle_spalten(),
        UniqueConstraint(*schluessel_spalten, SPALTE_VERSION),
        Index(
            f"uq_{name}_aktiv",
            *schluessel_spalten,
            unique=True,
            postgresql_where=text(f"{SPALTE_STATUS} = '{KatalogStatus.AKTIV.value}'"),
        ),
    )
