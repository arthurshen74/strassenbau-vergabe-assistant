"""One generic repository for the whole persisted catalog.

Thirteen near-identical lifecycle tables would be thirteen near-identical repositories, so
instead there is one repository parameterized by `KATALOG_REGISTRY` (table, natural-key column,
payload column set per entity). It moves `KatalogZeile` envelopes in and out; the seed and the
provider own the per-entity model↔payload mapping. Payloads are stored JSON-clean
(`model_dump(mode="json")`): Text/Numeric/Boolean columns accept the strings and Postgres
coerces them (Numeric reads back as Decimal), JSONB columns hold the parsed structures.

`neue_version` inserts the next version of a natural key as `entwurf`; `aktiviere` performs the
SCD-2 supersede (archive the current `aktiv` row of that key, then promote the draft), mirroring
`project_context_values.supersede` including the `clock_timestamp()` note. The two non-lifecycle
tables (Bauverfahren→Vorgang junction, supplier prices) have their own accessors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Table, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.katalog_ausfuehrungsarten import katalog_ausfuehrungsarten
from shared.db.tables.katalog_baustoffe import katalog_baustoffe
from shared.db.tables.katalog_bauverfahren import katalog_bauverfahren
from shared.db.tables.katalog_bauverfahren_vorgaenge import katalog_bauverfahren_vorgaenge
from shared.db.tables.katalog_betriebsarten import katalog_betriebsarten
from shared.db.tables.katalog_betriebskategorien import katalog_betriebskategorien
from shared.db.tables.katalog_formeln import katalog_formeln
from shared.db.tables.katalog_globale_variablen import katalog_globale_variablen
from shared.db.tables.katalog_leistung_bauverfahren import katalog_leistung_bauverfahren
from shared.db.tables.katalog_leistungen import katalog_leistungen
from shared.db.tables.katalog_lieferanten import katalog_lieferanten
from shared.db.tables.katalog_lieferanten_preise import katalog_lieferanten_preise
from shared.db.tables.katalog_lifecycle import (
    SPALTE_BENUTZER,
    SPALTE_BUNDLE_UUID,
    SPALTE_GUELTIG_AB,
    SPALTE_GUELTIG_BIS,
    SPALTE_STATUS,
    SPALTE_VERSION,
    SPALTE_ZEILE_UUID,
)
from shared.db.tables.katalog_maschinen import katalog_maschinen
from shared.db.tables.katalog_variablen import katalog_variablen
from shared.db.tables.katalog_vorgaenge import katalog_vorgaenge
from shared.models.katalog import KatalogEntitaet, KatalogPreis, KatalogStatus, KatalogZeile


@dataclass(frozen=True)
class EntitaetSpec:
    """How one catalog entity maps onto its table: the natural-key column and payload columns.

    `diskriminator` (a payload column, e.g. `gruppe`) extends the natural key: version/active
    scoping is per (schluessel, diskriminator) so the same key may recur once per discriminator."""

    tabelle: Table
    schluessel: str
    payload: tuple[str, ...]
    diskriminator: str | None = None


KATALOG_REGISTRY: dict[KatalogEntitaet, EntitaetSpec] = {
    KatalogEntitaet.LEISTUNGEN: EntitaetSpec(
        katalog_leistungen, "code", ("name", "beschreibung", "standard_kennung", "einheit")
    ),
    KatalogEntitaet.BAUVERFAHREN: EntitaetSpec(katalog_bauverfahren, "code", ("name",)),
    KatalogEntitaet.VORGAENGE: EntitaetSpec(
        katalog_vorgaenge,
        "code",
        (
            "name",
            "ausfuehrungsart_code",
            "betriebsart_code",
            "leistung_variable",
            "kosten_bindung",
            "kostenvariablen",
        ),
    ),
    KatalogEntitaet.AUSFUEHRUNGSARTEN: EntitaetSpec(
        katalog_ausfuehrungsarten, "code", ("name", "geraetebezug")
    ),
    KatalogEntitaet.BETRIEBSKATEGORIEN: EntitaetSpec(
        katalog_betriebskategorien, "code", ("bezeichnung", "beschreibung")
    ),
    KatalogEntitaet.BETRIEBSARTEN: EntitaetSpec(
        katalog_betriebsarten, "code", ("bezeichnung", "kategorie_code", "einheit", "beschreibung")
    ),
    KatalogEntitaet.FORMELN: EntitaetSpec(
        katalog_formeln, "name", ("ergebnis_variable", "ausdruck", "einheit")
    ),
    KatalogEntitaet.VARIABLEN: EntitaetSpec(
        katalog_variablen,
        "name",
        ("gruppe", "bezeichnung", "beschreibung", "einheit", "datentyp", "llm_kontext", "aufloesung"),
        diskriminator="gruppe",
    ),
    KatalogEntitaet.GLOBALE_VARIABLEN: EntitaetSpec(
        katalog_globale_variablen,
        "name",
        ("bezeichnung", "einheit", "datentyp", "ist_standort", "erforderlich", "ziel_variable", "rag_prompt"),
    ),
    KatalogEntitaet.BAUSTOFFE: EntitaetSpec(
        katalog_baustoffe,
        "code",
        (
            "name",
            "rohdichte_t_pro_m3",
            "verdichtungsfaktor",
            "kategorie",
            "koernung",
            "einheit",
            "basispreis_eur_pro_t",
            "basispreis_eur",
        ),
    ),
    KatalogEntitaet.LIEFERANTEN: EntitaetSpec(
        katalog_lieferanten, "code", ("name", "standort", "breitengrad", "laengengrad")
    ),
    KatalogEntitaet.MASCHINEN: EntitaetSpec(
        katalog_maschinen,
        "code",
        ("hersteller", "modell", "ausfuehrungsart_code", "eigenschaften", "leistungsprofile"),
    ),
    KatalogEntitaet.LEISTUNG_BAUVERFAHREN: EntitaetSpec(
        katalog_leistung_bauverfahren, "leistung_code", ("bauverfahren_codes",)
    ),
}


class KatalogRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    def _zeile(self, spec: EntitaetSpec, m: Mapping[str, Any]) -> KatalogZeile:
        return KatalogZeile(
            zeile_uuid=m[SPALTE_ZEILE_UUID],
            schluessel=m[spec.schluessel],
            version=m[SPALTE_VERSION],
            status=m[SPALTE_STATUS],
            bundle_uuid=m[SPALTE_BUNDLE_UUID],
            benutzer=m[SPALTE_BENUTZER],
            gueltig_ab=m[SPALTE_GUELTIG_AB],
            gueltig_bis=m[SPALTE_GUELTIG_BIS],
            payload={c: m[c] for c in spec.payload},
        )

    async def aktive(self, entitaet: KatalogEntitaet) -> list[KatalogZeile]:
        """Every `aktiv` row of an entity, ordered by natural key (deterministic)."""
        return await self.nach_status(entitaet, KatalogStatus.AKTIV)

    async def entwuerfe(self, entitaet: KatalogEntitaet) -> list[KatalogZeile]:
        """Every `entwurf` (draft) row of an entity."""
        return await self.nach_status(entitaet, KatalogStatus.ENTWURF)

    async def nach_status(
        self, entitaet: KatalogEntitaet, status: KatalogStatus
    ) -> list[KatalogZeile]:
        """Every row of an entity in a given lifecycle status, ordered by natural key."""
        spec = KATALOG_REGISTRY[entitaet]
        t = spec.tabelle
        stmt = (
            select(t).where(t.c[SPALTE_STATUS] == status.value).order_by(t.c[spec.schluessel])
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [self._zeile(spec, r) for r in rows]

    async def alle_versionen(
        self, entitaet: KatalogEntitaet, schluessel: str
    ) -> list[KatalogZeile]:
        """Every version of one natural key (any status), oldest first — the SCD-2 timeline (T32).

        For an entity with a discriminator (variablen: gruppe) a name may recur once per gruppe;
        all rows are returned, ordered by (version, gueltig_ab) so a shadowed name shows both."""
        spec = KATALOG_REGISTRY[entitaet]
        t = spec.tabelle
        stmt = (
            select(t)
            .where(t.c[spec.schluessel] == schluessel)
            .order_by(t.c[SPALTE_VERSION], t.c[SPALTE_GUELTIG_AB])
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [self._zeile(spec, r) for r in rows]

    async def nach_bundle(self, bundle_uuid: UUID) -> dict[KatalogEntitaet, list[KatalogZeile]]:
        """All rows carrying `bundle_uuid`, grouped by entity (any status)."""
        gruppen: dict[KatalogEntitaet, list[KatalogZeile]] = {}
        for entitaet, spec in KATALOG_REGISTRY.items():
            t = spec.tabelle
            stmt = select(t).where(t.c[SPALTE_BUNDLE_UUID] == bundle_uuid)
            rows = (await self.conn.execute(stmt)).mappings().all()
            if rows:
                gruppen[entitaet] = [self._zeile(spec, r) for r in rows]
        return gruppen

    async def offene_bundles(self) -> list[UUID]:
        """Distinct bundle_uuids that still have at least one `entwurf` row, newest first."""
        bundles: dict[UUID, Any] = {}
        for spec in KATALOG_REGISTRY.values():
            t = spec.tabelle
            stmt = (
                select(t.c[SPALTE_BUNDLE_UUID], func.max(t.c[SPALTE_GUELTIG_AB]))
                .where(
                    t.c[SPALTE_STATUS] == KatalogStatus.ENTWURF.value,
                    t.c[SPALTE_BUNDLE_UUID].is_not(None),
                )
                .group_by(t.c[SPALTE_BUNDLE_UUID])
            )
            for bundle_uuid, letzte in (await self.conn.execute(stmt)).all():
                if bundle_uuid not in bundles or letzte > bundles[bundle_uuid]:
                    bundles[bundle_uuid] = letzte
        return [b for b, _ in sorted(bundles.items(), key=lambda kv: kv[1], reverse=True)]

    def _schluessel_bedingung(self, spec: EntitaetSpec, schluessel: str, diskriminator_wert: Any):
        """WHERE terms that scope to one natural key, including the discriminator when present."""
        t = spec.tabelle
        bedingungen = [t.c[spec.schluessel] == schluessel]
        if spec.diskriminator is not None:
            bedingungen.append(t.c[spec.diskriminator] == diskriminator_wert)
        return bedingungen

    async def neue_version(
        self,
        entitaet: KatalogEntitaet,
        schluessel: str,
        payload: dict[str, Any],
        benutzer: str | None,
        bundle_uuid: UUID | None,
    ) -> KatalogZeile:
        """Insert the next version of `schluessel` as `entwurf`, sharing `bundle_uuid`."""
        spec = KATALOG_REGISTRY[entitaet]
        t = spec.tabelle
        diskriminator_wert = payload[spec.diskriminator] if spec.diskriminator else None
        next_version = (
            await self.conn.execute(
                select(func.coalesce(func.max(t.c[SPALTE_VERSION]), 0) + 1).where(
                    *self._schluessel_bedingung(spec, schluessel, diskriminator_wert)
                )
            )
        ).scalar_one()
        values = {
            spec.schluessel: schluessel,
            SPALTE_VERSION: next_version,
            SPALTE_STATUS: KatalogStatus.ENTWURF.value,
            SPALTE_BUNDLE_UUID: bundle_uuid,
            SPALTE_BENUTZER: benutzer,
            **{c: payload[c] for c in spec.payload},
        }
        row = (await self.conn.execute(insert(t).values(**values).returning(t))).mappings().one()
        return self._zeile(spec, row)

    async def aktiviere(self, entitaet: KatalogEntitaet, zeile_uuid: UUID) -> KatalogZeile:
        """Archive the current `aktiv` row of the draft's key, then promote the draft to `aktiv`.

        The archive precedes the promote so the one-`aktiv`-per-key partial index never sees two
        current rows. clock_timestamp() (not now()) advances within the transaction, so the
        archived row's gueltig_bis and the promoted row's gueltig_ab are the same instant — a
        gapless timeline even when several keys are activated in one UoW.
        """
        spec = KATALOG_REGISTRY[entitaet]
        t = spec.tabelle
        auswahl = [t.c[spec.schluessel]] + (
            [t.c[spec.diskriminator]] if spec.diskriminator else []
        )
        werte = (
            await self.conn.execute(select(*auswahl).where(t.c[SPALTE_ZEILE_UUID] == zeile_uuid))
        ).one()
        schluessel = werte[0]
        diskriminator_wert = werte[1] if spec.diskriminator else None
        now = (await self.conn.execute(select(func.clock_timestamp()))).scalar_one()
        await self.conn.execute(
            update(t)
            .where(
                *self._schluessel_bedingung(spec, schluessel, diskriminator_wert),
                t.c[SPALTE_STATUS] == KatalogStatus.AKTIV.value,
            )
            .values(**{SPALTE_STATUS: KatalogStatus.ARCHIVIERT.value, SPALTE_GUELTIG_BIS: now})
        )
        row = (
            await self.conn.execute(
                update(t)
                .where(t.c[SPALTE_ZEILE_UUID] == zeile_uuid)
                .values(**{SPALTE_STATUS: KatalogStatus.AKTIV.value, SPALTE_GUELTIG_AB: now})
                .returning(t)
            )
        ).mappings().one()
        return self._zeile(spec, row)

    async def archiviere(self, entitaet: KatalogEntitaet, zeile_uuid: UUID) -> None:
        """Discard a draft or retire an active row (status → archiviert, gueltig_bis = now)."""
        spec = KATALOG_REGISTRY[entitaet]
        t = spec.tabelle
        now = (await self.conn.execute(select(func.clock_timestamp()))).scalar_one()
        await self.conn.execute(
            update(t)
            .where(t.c[SPALTE_ZEILE_UUID] == zeile_uuid)
            .values(**{SPALTE_STATUS: KatalogStatus.ARCHIVIERT.value, SPALTE_GUELTIG_BIS: now})
        )

    # --- non-lifecycle children -------------------------------------------------------------- #

    async def vorgaenge_schreiben(self, bauverfahren_uuid: UUID, vorgang_codes: list[str]) -> None:
        """Write a Bauverfahren version's ordered Vorgang junction rows (reihenfolge = index)."""
        if not vorgang_codes:
            return
        await self.conn.execute(
            insert(katalog_bauverfahren_vorgaenge),
            [
                {
                    "bauverfahren_uuid": bauverfahren_uuid,
                    "reihenfolge": i,
                    "vorgang_code": code,
                }
                for i, code in enumerate(vorgang_codes)
            ],
        )

    async def vorgaenge_lesen(self, bauverfahren_uuid: UUID) -> list[str]:
        """The ordered Vorgang codes of one Bauverfahren version."""
        stmt = (
            select(katalog_bauverfahren_vorgaenge.c.vorgang_code)
            .where(katalog_bauverfahren_vorgaenge.c.bauverfahren_uuid == bauverfahren_uuid)
            .order_by(katalog_bauverfahren_vorgaenge.c.reihenfolge)
        )
        return list((await self.conn.execute(stmt)).scalars().all())

    async def preise_schreiben(self, preise: list[KatalogPreis]) -> None:
        """Append supplier price rows (immutable; a correction inserts a new row)."""
        if not preise:
            return
        await self.conn.execute(
            insert(katalog_lieferanten_preise),
            [p.model_dump() for p in preise],
        )

    async def preise(self) -> list[KatalogPreis]:
        """All supplier price rows, ordered by (lieferant, baustoff) for deterministic loads."""
        stmt = select(katalog_lieferanten_preise).order_by(
            katalog_lieferanten_preise.c.lieferant_code,
            katalog_lieferanten_preise.c.baustoff_code,
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [
            KatalogPreis(
                lieferant_code=r["lieferant_code"],
                baustoff_code=r["baustoff_code"],
                preis_eur_pro_t=r["preis_eur_pro_t"],
                gueltig_ab=r["gueltig_ab"],
                gueltig_bis=r["gueltig_bis"],
            )
            for r in rows
        ]

    async def ist_leer(self) -> bool:
        """True when no lifecycle catalog rows exist (a fresh, unseeded DB)."""
        for spec in KATALOG_REGISTRY.values():
            vorhanden = (
                await self.conn.execute(select(spec.tabelle.c[SPALTE_ZEILE_UUID]).limit(1))
            ).first()
            if vorhanden is not None:
                return False
        return True

    async def alles_leeren(self) -> None:
        """Delete every catalog row (lifecycle tables + junction + prices) for a reseed."""
        await self.conn.execute(delete(katalog_bauverfahren_vorgaenge))
        await self.conn.execute(delete(katalog_lieferanten_preise))
        for spec in KATALOG_REGISTRY.values():
            await self.conn.execute(delete(spec.tabelle))
