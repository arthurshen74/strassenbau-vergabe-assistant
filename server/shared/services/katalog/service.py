"""Bundle service (§7): validate → persist drafts → activate atomically → reload the provider.

Each write is one Unit-of-Work transaction. `entwurf_speichern` validates and inserts every row as
`entwurf` sharing one `bundle_uuid`; `bundle_aktivieren` re-validates against the *current* active
catalog, activates every draft row atomically, then reloads the provider on a fresh connection so
the running engine sees the new recipe; `bundle_verwerfen` discards the drafts (`verworfen`).

The service owns the engine (not a single connection) because activation must reload the provider
on a connection opened *after* the activation commits.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.unit_of_work import unit_of_work
from shared.models.katalog import (
    BundleBauverfahren,
    BundleBericht,
    BundleLieferant,
    BundlePreis,
    BundleVariable,
    BundleVorgang,
    BundleZeileAnsicht,
    BundleZustand,
    BundleZustandAnsicht,
    KatalogBundle,
    KatalogEntitaet,
    KatalogPreis,
    KatalogStatus,
    KatalogZeile,
    VariablenGruppe,
)
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository
from shared.services.kalkulation_v2.model import (
    Ausführungsart,
    Baustoff,
    Betriebsart,
    Betriebskategorie,
    Formel,
    Leistung,
    Maschine,
    VariableDefinition,
)
from shared.services.kalkulation_v2.provider import lade_katalog
from shared.services.katalog.validierung import lade_stand, pruefe_bundle

# Author recorded on catalog writes until real auth lands (mirrors the API route's dev principal).
DEFAULT_AUTOR = "kalkulator"


class BundleUngueltig(Exception):
    """A bundle failed validation; carries the report."""

    def __init__(self, bericht: BundleBericht) -> None:
        super().__init__("; ".join(bericht.fehler))
        self.bericht = bericht


class BundleNichtGefunden(Exception):
    """No draft rows carry the given bundle_uuid."""


def _payload(entitaet: KatalogEntitaet, record: dict) -> dict:
    return {c: record[c] for c in KATALOG_REGISTRY[entitaet].payload}


class KatalogService:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def pruefen(self, bundle: KatalogBundle) -> BundleBericht:
        """Validate a bundle against the current active catalog (no write)."""
        async with self.engine.connect() as conn:
            stand = await lade_stand(KatalogRepository(conn))
        return pruefe_bundle(bundle, stand)

    async def entwurf_speichern(self, bundle: KatalogBundle, benutzer: str) -> UUID:
        """Validate, then insert every bundle row as `entwurf` sharing one bundle_uuid."""
        bundle_uuid = uuid4()
        async with unit_of_work(self.engine) as uow:
            repo = uow.katalog
            bericht = pruefe_bundle(bundle, await lade_stand(repo))
            if not bericht.gueltig:
                raise BundleUngueltig(bericht)
            await self._schreibe_bundle(repo, bundle, benutzer, bundle_uuid)
            # Draft save touches the "last write" audit but does NOT bump the version (D4).
            await repo.stand_beruehren(benutzer, aktivierung=False)
        return bundle_uuid

    async def bundle_aktivieren(
        self, bundle_uuid: UUID, benutzer: str = DEFAULT_AUTOR
    ) -> BundleBericht:
        """Re-validate against the current active catalog, activate every draft row atomically,
        then reload the provider on a fresh connection."""
        async with unit_of_work(self.engine) as uow:
            repo = uow.katalog
            entwuerfe = await self._entwuerfe(repo, bundle_uuid)
            preis_entwuerfe = await repo.preise_nach_bundle(bundle_uuid, KatalogStatus.ENTWURF)
            if not entwuerfe and not preis_entwuerfe:
                raise BundleNichtGefunden(str(bundle_uuid))
            rekonstruiert = await self._bundle_aus_zeilen(repo, entwuerfe, preis_entwuerfe)
            bericht = pruefe_bundle(rekonstruiert, await lade_stand(repo))
            if not bericht.gueltig:
                raise BundleUngueltig(bericht)
            for entitaet, zeilen in entwuerfe.items():
                for z in zeilen:
                    await repo.aktiviere(entitaet, z.zeile_uuid)
            # Prices ride the same activation: each draft closes out an overlapping open-ended
            # active predecessor (D5) before it goes active.
            await repo.preise_aktivieren(bundle_uuid)
            # Activation is the ONLY write that bumps the version (D4).
            await repo.stand_beruehren(benutzer, aktivierung=True)
        async with self.engine.connect() as conn:
            await lade_katalog(conn)
        return bericht

    async def bundle_verwerfen(self, bundle_uuid: UUID, benutzer: str = DEFAULT_AUTOR) -> None:
        """Discard every draft row of the bundle (lifecycle rows + price drafts) as `verworfen`."""
        async with unit_of_work(self.engine) as uow:
            repo = uow.katalog
            entwuerfe = await self._entwuerfe(repo, bundle_uuid)
            preis_entwuerfe = await repo.preise_nach_bundle(bundle_uuid, KatalogStatus.ENTWURF)
            if not entwuerfe and not preis_entwuerfe:
                raise BundleNichtGefunden(str(bundle_uuid))
            for entitaet, zeilen in entwuerfe.items():
                for z in zeilen:
                    await repo.verwirf(entitaet, z.zeile_uuid)
            await repo.preise_verwerfen(bundle_uuid)
            await repo.stand_beruehren(benutzer, aktivierung=False)

    # --- reads -------------------------------------------------------------------------------- #

    async def aktive(self, entitaet: KatalogEntitaet) -> list[KatalogZeile]:
        async with self.engine.connect() as conn:
            return await KatalogRepository(conn).aktive(entitaet)

    async def versionen(
        self, entitaet: KatalogEntitaet, schluessel: str
    ) -> list[KatalogZeile]:
        """Every version of one natural key (any status), oldest first — the SCD-2 timeline that
        backs the Katalog UI's Versionshistorie (rate-change ledger)."""
        async with self.engine.connect() as conn:
            return await KatalogRepository(conn).alle_versionen(entitaet, schluessel)

    async def bundle_zustand(self, bundle_uuid: UUID) -> BundleZustandAnsicht:
        """The confirm card's state re-query: the bundle's rows (lifecycle + prices) plus the
        derived zustand — any entwurf → offen; else any aktiv → aktiviert; else any verworfen →
        verworfen; else geschlossen (activated, later superseded)."""
        async with self.engine.connect() as conn:
            repo = KatalogRepository(conn)
            gruppen = await repo.nach_bundle(bundle_uuid)
            preise = await repo.preise_nach_bundle(bundle_uuid)
        zeilen = [
            BundleZeileAnsicht(entitaet=entitaet.value, schluessel=z.schluessel, status=z.status)
            for entitaet, zs in gruppen.items()
            for z in zs
        ]
        zeilen += [
            BundleZeileAnsicht(
                entitaet="preise",
                schluessel=f"{p.lieferant_code}/{p.baustoff_code}",
                status=p.status,
            )
            for p in preise
        ]
        stati = {z.status for z in zeilen}
        if KatalogStatus.ENTWURF in stati:
            zustand = BundleZustand.OFFEN
        elif KatalogStatus.AKTIV in stati:
            zustand = BundleZustand.AKTIVIERT
        elif KatalogStatus.VERWORFEN in stati:
            zustand = BundleZustand.VERWORFEN
        else:
            zustand = BundleZustand.GESCHLOSSEN
        return BundleZustandAnsicht(zustand=zustand, zeilen=zeilen)

    async def entwuerfe_nach_bundle(self) -> dict[UUID, dict[KatalogEntitaet, list[KatalogZeile]]]:
        """All open draft bundles, grouped by bundle_uuid then entity."""
        async with self.engine.connect() as conn:
            repo = KatalogRepository(conn)
            gruppen: dict[UUID, dict[KatalogEntitaet, list[KatalogZeile]]] = {}
            for bundle_uuid in await repo.offene_bundles():
                gruppen[bundle_uuid] = await self._entwuerfe(repo, bundle_uuid)
            return gruppen

    async def neu_laden(self) -> dict[str, int] | None:
        """Re-read the persisted catalog into the running engine's module dicts, so edits that did
        not go through a bundle activation (external tools, manual fixes) become visible without a
        restart. Returns the per-entity counts, or None when the katalog tables are empty (the
        provider keeps the fixture data)."""
        async with self.engine.connect() as conn:
            return await lade_katalog(conn)

    # --- helpers ------------------------------------------------------------------------------ #

    @staticmethod
    async def _entwuerfe(
        repo: KatalogRepository, bundle_uuid: UUID
    ) -> dict[KatalogEntitaet, list[KatalogZeile]]:
        gruppen = await repo.nach_bundle(bundle_uuid)
        entwuerfe = {
            entitaet: [z for z in zeilen if z.status == KatalogStatus.ENTWURF]
            for entitaet, zeilen in gruppen.items()
        }
        return {entitaet: zeilen for entitaet, zeilen in entwuerfe.items() if zeilen}

    async def _schreibe_bundle(
        self, repo: KatalogRepository, bundle: KatalogBundle, benutzer: str, bundle_uuid: UUID
    ) -> None:
        async def draft(entitaet: KatalogEntitaet, schluessel: str, payload: dict) -> KatalogZeile:
            return await repo.neue_version(entitaet, schluessel, payload, benutzer, bundle_uuid)

        for lg in bundle.leistungen:
            await draft(KatalogEntitaet.LEISTUNGEN, lg.code, _payload(KatalogEntitaet.LEISTUNGEN, lg.model_dump(mode="json")))
        for a in bundle.ausfuehrungsarten:
            await draft(KatalogEntitaet.AUSFUEHRUNGSARTEN, a.code, _payload(KatalogEntitaet.AUSFUEHRUNGSARTEN, a.model_dump(mode="json")))
        for k in bundle.betriebskategorien:
            await draft(KatalogEntitaet.BETRIEBSKATEGORIEN, k.code, _payload(KatalogEntitaet.BETRIEBSKATEGORIEN, k.model_dump(mode="json")))
        for b in bundle.betriebsarten:
            await draft(KatalogEntitaet.BETRIEBSARTEN, b.code, _payload(KatalogEntitaet.BETRIEBSARTEN, b.model_dump(mode="json")))
        for f in bundle.formeln:
            await draft(KatalogEntitaet.FORMELN, f.name, _payload(KatalogEntitaet.FORMELN, f.model_dump(mode="json")))
        for bst in bundle.baustoffe:
            await draft(KatalogEntitaet.BAUSTOFFE, bst.code, _payload(KatalogEntitaet.BAUSTOFFE, bst.model_dump(mode="json")))
        for m in bundle.maschinen:
            await draft(KatalogEntitaet.MASCHINEN, m.code, _payload(KatalogEntitaet.MASCHINEN, m.model_dump(mode="json")))
        for lief in bundle.lieferanten:
            await draft(KatalogEntitaet.LIEFERANTEN, lief.code, _payload(KatalogEntitaet.LIEFERANTEN, lief.model_dump(mode="json")))

        for bv in bundle.variablen:
            record = bv.definition.model_dump(mode="json") | {"gruppe": bv.gruppe.value}
            await draft(KatalogEntitaet.VARIABLEN, bv.definition.name, _payload(KatalogEntitaet.VARIABLEN, record))

        for v in bundle.vorgaenge:
            await draft(KatalogEntitaet.VORGAENGE, v.code, _payload(KatalogEntitaet.VORGAENGE, v.model_dump(mode="json")))
        for b in bundle.bauverfahren:
            z = await draft(KatalogEntitaet.BAUVERFAHREN, b.code, {"name": b.name})
            await repo.vorgaenge_schreiben(z.zeile_uuid, b.vorgang_codes)
        for leistung_code, bauverfahren_codes in bundle.leistung_bauverfahren.items():
            await draft(KatalogEntitaet.LEISTUNG_BAUVERFAHREN, leistung_code, {"bauverfahren_codes": bauverfahren_codes})

        # Prices are immutable value rows, not lifecycle entities: written as draft price rows
        # carrying the bundle_uuid so they activate/discard with the bundle.
        preise = [
            KatalogPreis(
                lieferant_code=p.lieferant_code,
                baustoff_code=p.baustoff_code,
                preis_eur_pro_t=p.preis_eur_pro_t,
                gueltig_ab=p.gueltig_ab,
                gueltig_bis=p.gueltig_bis,
                status=KatalogStatus.ENTWURF,
                bundle_uuid=bundle_uuid,
                benutzer=benutzer,
            )
            for p in bundle.preise
        ]
        await repo.preise_schreiben(preise)

    @staticmethod
    async def _bundle_aus_zeilen(
        repo: KatalogRepository,
        entwuerfe: dict[KatalogEntitaet, list[KatalogZeile]],
        preis_entwuerfe: list[KatalogPreis],
    ) -> KatalogBundle:
        """Reconstruct a KatalogBundle from its draft rows, for re-validation on activation."""

        def modelle(entitaet: KatalogEntitaet, cls, schluessel_feld: str):
            return [
                cls.model_validate({schluessel_feld: z.schluessel, **z.payload})
                for z in entwuerfe.get(entitaet, [])
            ]

        variablen = [
            BundleVariable(
                gruppe=VariablenGruppe(z.payload["gruppe"]),
                definition=VariableDefinition.model_validate(
                    {"name": z.schluessel, **{k: v for k, v in z.payload.items() if k != "gruppe"}}
                ),
            )
            for z in entwuerfe.get(KatalogEntitaet.VARIABLEN, [])
        ]
        vorgaenge = [
            BundleVorgang.model_validate({"code": z.schluessel, **z.payload})
            for z in entwuerfe.get(KatalogEntitaet.VORGAENGE, [])
        ]
        bauverfahren = [
            BundleBauverfahren(
                code=z.schluessel,
                name=z.payload["name"],
                vorgang_codes=await repo.vorgaenge_lesen(z.zeile_uuid),
            )
            for z in entwuerfe.get(KatalogEntitaet.BAUVERFAHREN, [])
        ]
        return KatalogBundle(
            leistungen=modelle(KatalogEntitaet.LEISTUNGEN, Leistung, "code"),
            bauverfahren=bauverfahren,
            vorgaenge=vorgaenge,
            ausfuehrungsarten=modelle(KatalogEntitaet.AUSFUEHRUNGSARTEN, Ausführungsart, "code"),
            betriebskategorien=modelle(KatalogEntitaet.BETRIEBSKATEGORIEN, Betriebskategorie, "code"),
            betriebsarten=modelle(KatalogEntitaet.BETRIEBSARTEN, Betriebsart, "code"),
            formeln=modelle(KatalogEntitaet.FORMELN, Formel, "name"),
            variablen=variablen,
            baustoffe=modelle(KatalogEntitaet.BAUSTOFFE, Baustoff, "code"),
            maschinen=modelle(KatalogEntitaet.MASCHINEN, Maschine, "code"),
            lieferanten=modelle(KatalogEntitaet.LIEFERANTEN, BundleLieferant, "code"),
            preise=[
                BundlePreis(
                    lieferant_code=p.lieferant_code,
                    baustoff_code=p.baustoff_code,
                    preis_eur_pro_t=p.preis_eur_pro_t,
                    gueltig_ab=p.gueltig_ab,
                    gueltig_bis=p.gueltig_bis,
                )
                for p in preis_entwuerfe
            ],
            leistung_bauverfahren={
                z.schluessel: z.payload["bauverfahren_codes"]
                for z in entwuerfe.get(KatalogEntitaet.LEISTUNG_BAUVERFAHREN, [])
            },
        )
