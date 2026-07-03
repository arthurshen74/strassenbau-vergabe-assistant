"""Integration test (§10.5): a bundle draft → activate → provider reload → new recipe calculable.

Uses the session engine (the KatalogService commits through its own connections), so it seeds and
cleans up explicitly and restores the in-place-refilled module dicts via `zustand_sichern`.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBauverfahren,
    BundleVorgang,
    KatalogEntitaet,
    KatalogBundle,
)
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.model import Formel, Kostenart, Leistung
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.store import kalkuliere
from shared.services.katalog.service import KatalogService

from scripts.check_katalog_parity import zustand_sichern
from scripts.seed.seed_katalog import seed_katalog


def _neues_rezept() -> KatalogBundle:
    """A self-contained new Leistung: one Vorgang whose cost is a bundle Formel over booked area."""
    return KatalogBundle(
        leistungen=[Leistung(code="L_KATALOG_TEST", name="Katalog-Teststrecke", einheit="m2")],
        formeln=[
            Formel(
                name="mk_katalog_test",
                ergebnis_variable="mk_katalog_test",
                ausdruck="flaeche_m2 * 5",
                einheit="€",
            )
        ],
        vorgaenge=[
            BundleVorgang(
                code="V_KATALOG_TEST",
                name="Katalog-Testvorgang",
                kostenvariablen={Kostenart.MASCHINE: "mk_katalog_test"},
            )
        ],
        bauverfahren=[
            BundleBauverfahren(code="BV_KATALOG_TEST", name="Katalog-Testverfahren", vorgang_codes=["V_KATALOG_TEST"])
        ],
        leistung_bauverfahren={"L_KATALOG_TEST": ["BV_KATALOG_TEST"]},
    )


async def test_bundle_aktivierung_macht_rezept_kalkulierbar(engine: AsyncEngine) -> None:
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            bundle_uuid = await service.entwurf_speichern(_neues_rezept(), benutzer="test")

            # Draft is not yet in the active catalog.
            aktive_leistungen = {z.schluessel for z in await service.aktive(KatalogEntitaet.LEISTUNGEN)}
            assert "L_KATALOG_TEST" not in aktive_leistungen

            bericht = await service.bundle_aktivieren(bundle_uuid)
            assert bericht.gueltig, bericht.fehler

            # The provider reloaded: the new recipe is calculable through the engine.
            ergebnis = kalkuliere(Position(oz="TEST-01", leistung_key="L_KATALOG_TEST", menge=Decimal("100")))
            assert ergebnis["bauverfahren"] == "BV_KATALOG_TEST"
            assert ergebnis["ekt_eur"] == Decimal("500.00")
            assert ergebnis["ep_eur"] == Decimal("5.00")
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()


async def test_neu_laden_macht_externe_aenderungen_sichtbar(engine: AsyncEngine) -> None:
    """An edit that bypasses the bundle service (repo-level supersede, as an external CRUD tool
    would do) is invisible to the running engine until `neu_laden` re-reads the catalog."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            geladen = await service.neu_laden()
            assert geladen is not None and geladen["leistungen"] == len(LEISTUNGEN)

            # External edit: supersede a Leistung directly at the repository, no bundle.
            async with engine.begin() as conn:
                repo = KatalogRepository(conn)
                zeile = next(
                    z for z in await repo.aktive(KatalogEntitaet.LEISTUNGEN) if z.schluessel == "L_FSS"
                )
                neu = await repo.neue_version(
                    KatalogEntitaet.LEISTUNGEN,
                    "L_FSS",
                    {**zeile.payload, "name": "FSS (extern geändert)"},
                    benutzer="test",
                    bundle_uuid=None,
                )
                await repo.aktiviere(KatalogEntitaet.LEISTUNGEN, neu.zeile_uuid)

            assert LEISTUNGEN["L_FSS"].name != "FSS (extern geändert)"  # engine still on old state
            await service.neu_laden()
            assert LEISTUNGEN["L_FSS"].name == "FSS (extern geändert)"
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()
