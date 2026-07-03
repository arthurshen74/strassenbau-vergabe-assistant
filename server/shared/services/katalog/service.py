"""Bundle service (§7): validate → persist drafts → activate atomically → reload the provider.

Each write is one Unit-of-Work transaction. `entwurf_speichern` validates and inserts every row as
`entwurf` sharing one `bundle_uuid`; `bundle_aktivieren` re-validates against the *current* active
catalog, activates every draft row atomically, then reloads the provider on a fresh connection so
the running engine sees the new recipe; `bundle_verwerfen` archives the drafts.

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
    BundleVariable,
    BundleVorgang,
    KatalogEntitaet,
    KatalogStatus,
    KatalogZeile,
    KatalogBundle,
    VariablenGruppe,
)
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    AufloesungsSchritt,
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


class BundleUngueltig(Exception):
    """A bundle failed validation; carries the report."""

    def __init__(self, bericht: BundleBericht) -> None:
        super().__init__("; ".join(bericht.fehler))
        self.bericht = bericht


class BundleNichtGefunden(Exception):
    """No draft rows carry the given bundle_uuid."""


def _payload(entitaet: KatalogEntitaet, record: dict) -> dict:
    return {c: record[c] for c in KATALOG_REGISTRY[entitaet].payload}


def _formel_variable(name: str, einheit: str | None) -> VariableDefinition:
    """The FORMEL-gruppe variable a Formel implies (mirrors the `formel()` fixture helper)."""
    return VariableDefinition(
        name=name,
        bezeichnung=name,
        einheit=einheit,
        aufloesung=[AufloesungsSchritt(methode=AufloesungsMethode.FORMEL, formel_name=name)],
    )


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
        return bundle_uuid

    async def bundle_aktivieren(self, bundle_uuid: UUID) -> BundleBericht:
        """Re-validate against the current active catalog, activate every draft row atomically,
        then reload the provider on a fresh connection."""
        async with unit_of_work(self.engine) as uow:
            repo = uow.katalog
            entwuerfe = await self._entwuerfe(repo, bundle_uuid)
            if not entwuerfe:
                raise BundleNichtGefunden(str(bundle_uuid))
            rekonstruiert = await self._bundle_aus_zeilen(repo, entwuerfe)
            bericht = pruefe_bundle(rekonstruiert, await lade_stand(repo))
            if not bericht.gueltig:
                raise BundleUngueltig(bericht)
            for entitaet, zeilen in entwuerfe.items():
                for z in zeilen:
                    await repo.aktiviere(entitaet, z.zeile_uuid)
        async with self.engine.connect() as conn:
            await lade_katalog(conn)
        return bericht

    async def bundle_verwerfen(self, bundle_uuid: UUID) -> None:
        """Archive every draft row of the bundle."""
        async with unit_of_work(self.engine) as uow:
            repo = uow.katalog
            entwuerfe = await self._entwuerfe(repo, bundle_uuid)
            if not entwuerfe:
                raise BundleNichtGefunden(str(bundle_uuid))
            for entitaet, zeilen in entwuerfe.items():
                for z in zeilen:
                    await repo.archiviere(entitaet, z.zeile_uuid)

    # --- reads -------------------------------------------------------------------------------- #

    async def aktive(self, entitaet: KatalogEntitaet) -> list[KatalogZeile]:
        async with self.engine.connect() as conn:
            return await KatalogRepository(conn).aktive(entitaet)

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

        explizite_formel_vars = {
            bv.definition.name for bv in bundle.variablen if bv.gruppe == VariablenGruppe.FORMEL
        }
        for bv in bundle.variablen:
            record = bv.definition.model_dump(mode="json") | {"gruppe": bv.gruppe.value}
            await draft(KatalogEntitaet.VARIABLEN, bv.definition.name, _payload(KatalogEntitaet.VARIABLEN, record))
        for f in bundle.formeln:
            if f.name in explizite_formel_vars:
                continue
            record = _formel_variable(f.name, f.einheit).model_dump(mode="json") | {"gruppe": VariablenGruppe.FORMEL.value}
            await draft(KatalogEntitaet.VARIABLEN, f.name, _payload(KatalogEntitaet.VARIABLEN, record))

        for v in bundle.vorgaenge:
            await draft(KatalogEntitaet.VORGAENGE, v.code, _payload(KatalogEntitaet.VORGAENGE, v.model_dump(mode="json")))
        for b in bundle.bauverfahren:
            z = await draft(KatalogEntitaet.BAUVERFAHREN, b.code, {"name": b.name})
            await repo.vorgaenge_schreiben(z.zeile_uuid, b.vorgang_codes)
        for leistung_code, bauverfahren_codes in bundle.leistung_bauverfahren.items():
            await draft(KatalogEntitaet.LEISTUNG_BAUVERFAHREN, leistung_code, {"bauverfahren_codes": bauverfahren_codes})

    @staticmethod
    async def _bundle_aus_zeilen(
        repo: KatalogRepository, entwuerfe: dict[KatalogEntitaet, list[KatalogZeile]]
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
            leistung_bauverfahren={
                z.schluessel: z.payload["bauverfahren_codes"]
                for z in entwuerfe.get(KatalogEntitaet.LEISTUNG_BAUVERFAHREN, [])
            },
        )
