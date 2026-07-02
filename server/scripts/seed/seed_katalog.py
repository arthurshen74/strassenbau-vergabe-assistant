"""Seed the persisted catalog from the `kalkulation_v2` fixture modules.

Writes every catalog entity as `version=1, status=aktiv, benutzer="seed", bundle_uuid=NULL`,
plus the Bauverfahren→Vorgang junction (from each recipe's Vorgang order) and the supplier price
history (from `lade_preise`). The write is one Unit-of-Work transaction. Idempotent guard: aborts
if any `katalog_*` table already holds rows; `--reset` truncates them all first and reseeds.

    uv run python -m scripts.seed.seed_katalog [--reset]
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import settings
from shared.db.unit_of_work import unit_of_work
from shared.models.katalog import KatalogEntitaet, KatalogPreis, VariablenGruppe
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository

# Importing store runs `lade_preise(BAUSTOFFE, LIEFERANTEN)` at import, so the supplier price
# lists are populated exactly as the running app sees them before we read them below.
from shared.services.kalkulation_v2 import store  # noqa: F401  -- side effect: lade_preise
from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.betriebsarten import BETRIEBSARTEN, BETRIEBSKATEGORIEN
from shared.services.kalkulation_v2.formel import FORMELN, FORMEL_VARIABLEN
from shared.services.kalkulation_v2.globale_variablen import GLOBALE_VARIABLEN
from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN
from shared.services.kalkulation_v2.leistung_bauverfahren import LEISTUNG_BAUVERFAHREN
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.lieferanten import LIEFERANTEN
from shared.services.kalkulation_v2.maschinen import MASCHINEN
from shared.services.kalkulation_v2.materialien import BAUSTOFFE
from shared.services.kalkulation_v2.stammdaten import STAMMDATEN_VARIABLEN
from shared.services.kalkulation_v2.vorgaenge import VORGAENGE


def _payload(entitaet: KatalogEntitaet, record: dict) -> dict:
    """Pick the entity's payload columns from a JSON-clean model record."""
    return {c: record[c] for c in KATALOG_REGISTRY[entitaet].payload}


async def _schreibe_aktiv(
    repo: KatalogRepository, entitaet: KatalogEntitaet, schluessel: str, payload: dict
) -> None:
    z = await repo.neue_version(entitaet, schluessel, payload, benutzer="seed", bundle_uuid=None)
    await repo.aktiviere(entitaet, z.zeile_uuid)


async def seed_katalog(repo: KatalogRepository) -> dict[str, int]:
    """Write the full fixture catalog as version-1 active rows. Assumes empty katalog tables."""
    zaehler: dict[str, int] = {}

    async def plain(entitaet: KatalogEntitaet, modelle, schluessel_attr: str) -> None:
        for m in modelle:
            record = m.model_dump(mode="json")
            await _schreibe_aktiv(repo, entitaet, getattr(m, schluessel_attr), _payload(entitaet, record))
        zaehler[entitaet.value] = len(list(modelle))

    # Order is free for the seed (no cross-entity FK except the junction, written with its parent).
    await plain(KatalogEntitaet.BETRIEBSKATEGORIEN, list(BETRIEBSKATEGORIEN.values()), "code")
    await plain(KatalogEntitaet.BETRIEBSARTEN, list(BETRIEBSARTEN.values()), "code")
    await plain(KatalogEntitaet.AUSFUEHRUNGSARTEN, list(AUSFUEHRUNGSARTEN.values()), "code")
    await plain(KatalogEntitaet.FORMELN, list(FORMELN.values()), "name")
    await plain(KatalogEntitaet.GLOBALE_VARIABLEN, list(GLOBALE_VARIABLEN.values()), "name")
    await plain(KatalogEntitaet.BAUSTOFFE, list(BAUSTOFFE.values()), "code")
    await plain(KatalogEntitaet.MASCHINEN, list(MASCHINEN.values()), "code")
    await plain(KatalogEntitaet.LEISTUNGEN, list(LEISTUNGEN.values()), "code")

    # Variablen: three fixture sources, each carrying its gruppe discriminator.
    n_var = 0
    for gruppe, quelle in (
        (VariablenGruppe.STAMMDATEN, STAMMDATEN_VARIABLEN),
        (VariablenGruppe.KONTEXT, KONTEXT_VARIABLEN),
        (VariablenGruppe.FORMEL, FORMEL_VARIABLEN),
    ):
        for vardef in quelle.values():
            record = vardef.model_dump(mode="json") | {"gruppe": gruppe.value}
            await _schreibe_aktiv(
                repo, KatalogEntitaet.VARIABLEN, vardef.name, _payload(KatalogEntitaet.VARIABLEN, record)
            )
            n_var += 1
    zaehler[KatalogEntitaet.VARIABLEN.value] = n_var

    # Vorgänge: the embedded Ausführungsart is stored by code (re-embedded on load).
    for v in VORGAENGE.values():
        record = v.model_dump(mode="json") | {
            "ausfuehrungsart_code": v.ausfuehrungsart.code if v.ausfuehrungsart else None
        }
        await _schreibe_aktiv(
            repo, KatalogEntitaet.VORGAENGE, v.code, _payload(KatalogEntitaet.VORGAENGE, record)
        )
    zaehler[KatalogEntitaet.VORGAENGE.value] = len(VORGAENGE)

    # Bauverfahren: name row + ordered Vorgang junction (by code) tied to this version.
    n_junction = 0
    for bv in BAUVERFAHREN.values():
        z = await repo.neue_version(
            KatalogEntitaet.BAUVERFAHREN, bv.code, {"name": bv.name}, benutzer="seed", bundle_uuid=None
        )
        await repo.aktiviere(KatalogEntitaet.BAUVERFAHREN, z.zeile_uuid)
        vorgang_codes = [vg.code for vg in bv.vorgaenge]
        await repo.vorgaenge_schreiben(z.zeile_uuid, vorgang_codes)
        n_junction += len(vorgang_codes)
    zaehler[KatalogEntitaet.BAUVERFAHREN.value] = len(BAUVERFAHREN)
    zaehler["bauverfahren_vorgaenge"] = n_junction

    # Lieferanten: the row + the supplier's full price list (curated + gap-filled).
    preise: list[KatalogPreis] = []
    for lief in LIEFERANTEN.values():
        record = lief.model_dump(mode="json")
        await _schreibe_aktiv(
            repo, KatalogEntitaet.LIEFERANTEN, lief.code, _payload(KatalogEntitaet.LIEFERANTEN, record)
        )
        for p in lief.preise:
            preise.append(
                KatalogPreis(
                    lieferant_code=lief.code,
                    baustoff_code=p.baustoff_code,
                    preis_eur_pro_t=p.preis_eur_pro_t,
                    gueltig_ab=p.gueltig_ab,
                    gueltig_bis=p.gueltig_bis,
                )
            )
    zaehler[KatalogEntitaet.LIEFERANTEN.value] = len(LIEFERANTEN)
    await repo.preise_schreiben(preise)
    zaehler["lieferanten_preise"] = len(preise)

    # Leistung → candidate Bauverfahren mapping (ordered list; first = default).
    for leistung_code, bauverfahren_codes in LEISTUNG_BAUVERFAHREN.items():
        await _schreibe_aktiv(
            repo,
            KatalogEntitaet.LEISTUNG_BAUVERFAHREN,
            leistung_code,
            {"bauverfahren_codes": bauverfahren_codes},
        )
    zaehler[KatalogEntitaet.LEISTUNG_BAUVERFAHREN.value] = len(LEISTUNG_BAUVERFAHREN)

    return zaehler


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the katalog_* tables from the fixtures.")
    parser.add_argument("--reset", action="store_true", help="truncate all katalog_* tables first")
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    try:
        async with unit_of_work(engine) as uow:
            repo = uow.katalog
            if args.reset:
                await repo.alles_leeren()
            elif not await repo.ist_leer():
                print("katalog_* tables already populated — pass --reset to truncate and reseed.")
                return
            zaehler = await seed_katalog(repo)
        for name, n in zaehler.items():
            print(f"  {name:28} {n:>5}")
        print(f"seeded {sum(zaehler.values())} rows across {len(zaehler)} groups.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
