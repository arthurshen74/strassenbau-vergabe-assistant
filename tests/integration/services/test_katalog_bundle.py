"""Integration test (§10.5): a bundle draft → activate → provider reload → new recipe calculable.

Uses the session engine (the KatalogService commits through its own connections), so it seeds and
cleans up explicitly and restores the in-place-refilled module dicts via `zustand_sichern`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBauverfahren,
    BundleLieferant,
    BundlePreis,
    BundleVariable,
    BundleVorgang,
    BundleZustand,
    KatalogBundle,
    KatalogEntitaet,
    KatalogStatus,
    VariablenGruppe,
)
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2 import lieferanten as m_lief
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    AufloesungsSchritt,
    Baustoff,
    FormelInstanz,
    Kostenart,
    Leistung,
    VariableDefinition,
    VorgangRechnung,
)
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.store import kalkuliere
from shared.services.katalog.service import KatalogService

from scripts.check_katalog_parity import zustand_sichern
from scripts.seed.seed_katalog import seed_katalog


def _neues_rezept() -> KatalogBundle:
    """A self-contained new Leistung whose Maschine cost line INSTANTIATES the seeded base formula
    F_KOSTEN_SATZ over the booked area: menge = kontext.flaeche_m2, satz = 5 €/m² (a literal). No
    minted formula — search-before-create reuse of a base formula."""
    return KatalogBundle(
        leistungen=[Leistung(code="L_KATALOG_TEST", name="Katalog-Teststrecke", einheit="m2")],
        vorgaenge=[
            BundleVorgang(
                code="V_KATALOG_TEST",
                name="Katalog-Testvorgang",
                rechnung=VorgangRechnung(
                    kosten={
                        Kostenart.MASCHINE: [
                            FormelInstanz(
                                formel="F_KOSTEN_SATZ",
                                bindung={"menge": "kontext.flaeche_m2", "satz": "5"},
                            )
                        ]
                    }
                ),
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


def _rate_entwurf() -> KatalogBundle:
    """A trivial, self-contained draft (one new stammdaten KONSTANTE) — a valid discard target."""
    return KatalogBundle(
        variablen=[
            BundleVariable(
                gruppe=VariablenGruppe.STAMMDATEN,
                definition=VariableDefinition(
                    name="test_discard_rate_eur",
                    bezeichnung="Discard-Test-Satz",
                    beschreibung="Wegwerf-Testsatz für den Verwerfen-Pfad; ohne Kalkulationsbezug.",
                    einheit="€",
                    aufloesung=[
                        AufloesungsSchritt(
                            methode=AufloesungsMethode.KONSTANTE, konstante=Decimal("1")
                        )
                    ],
                ),
            )
        ]
    )


async def test_katalog_stand_bump_matrix(engine: AsyncEngine) -> None:
    """§10.2: seed → version 1; draft save → version unchanged, aktualisiert_am moves; activate →
    version +1; discard → version unchanged."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)

            async def stand():
                async with engine.connect() as conn:
                    return await KatalogRepository(conn).stand_lesen()

            s0 = await stand()
            assert s0 is not None and s0.version == 1 and s0.benutzer == "seed"

            # Draft save: version unchanged, last-touched moves, benutzer updated.
            bundle_uuid = await service.entwurf_speichern(_neues_rezept(), benutzer="tester")
            s1 = await stand()
            assert s1.version == 1
            assert s1.aktualisiert_am > s0.aktualisiert_am
            assert s1.benutzer == "tester"

            # Activate: the only write that bumps the version.
            await service.bundle_aktivieren(bundle_uuid, benutzer="tester")
            s2 = await stand()
            assert s2.version == 2

            # Discard: version unchanged.
            zweiter = await service.entwurf_speichern(_rate_entwurf(), benutzer="tester")
            await service.bundle_verwerfen(zweiter, benutzer="tester")
            s3 = await stand()
            assert s3.version == 2
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()


async def test_preis_closeout_bei_aktivierung(engine: AsyncEngine) -> None:
    """§10.3: activating a price that overlaps an open-ended active predecessor closes the
    predecessor's gueltig_bis to the day before the new gueltig_ab; the new price resolves from its
    Stichtag on; both rows survive (history intact)."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)

            # Bundle A: a fresh Lieferant + Baustoff + open-ended price P1.
            grund = KatalogBundle(
                lieferanten=[BundleLieferant(code="LIEF_CLOSEOUT", name="Closeout-Test")],
                baustoffe=[
                    Baustoff(
                        code="B_CLOSEOUT",
                        name="Closeout-Baustoff",
                        rohdichte_t_pro_m3=Decimal("2.4"),
                        einheit="t",
                    )
                ],
                preise=[
                    BundlePreis(
                        lieferant_code="LIEF_CLOSEOUT",
                        baustoff_code="B_CLOSEOUT",
                        preis_eur_pro_t=Decimal("15.00"),
                        gueltig_ab=date(2026, 1, 1),
                    )
                ],
            )
            await service.bundle_aktivieren(await service.entwurf_speichern(grund, benutzer="t"))

            # Bundle B: a new price P2 for the same pair, starting later (price-only bundle).
            neu = KatalogBundle(
                preise=[
                    BundlePreis(
                        lieferant_code="LIEF_CLOSEOUT",
                        baustoff_code="B_CLOSEOUT",
                        preis_eur_pro_t=Decimal("20.00"),
                        gueltig_ab=date(2026, 8, 1),
                    )
                ]
            )
            await service.bundle_aktivieren(await service.entwurf_speichern(neu, benutzer="t"))

            # The provider reloaded: the new price resolves from its Stichtag on, the predecessor
            # before it.
            lief = m_lief.LIEFERANTEN["LIEF_CLOSEOUT"]
            assert lief.preis_fuer("B_CLOSEOUT", date(2026, 8, 1)) == Decimal("20.00")
            assert lief.preis_fuer("B_CLOSEOUT", date(2026, 3, 1)) == Decimal("15.00")

            # History intact: both rows present, the predecessor closed to the day before P2.
            async with engine.connect() as conn:
                preise = await KatalogRepository(conn).preise()
            paar = [
                p for p in preise
                if p.lieferant_code == "LIEF_CLOSEOUT" and p.baustoff_code == "B_CLOSEOUT"
            ]
            assert len(paar) == 2
            p1 = next(p for p in paar if p.gueltig_ab == date(2026, 1, 1))
            assert p1.gueltig_bis == date(2026, 7, 31)
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()


async def test_preis_closeout_zwei_preise_gleiches_paar_in_einem_bundle(engine: AsyncEngine) -> None:
    """Two prices for the SAME (Lieferant, Baustoff) in ONE bundle — deliberately listed
    later-first — must activate earliest-validity-first so each closes its predecessor: afterwards
    exactly one open-ended active price exists and Stichtag resolution is unambiguous."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            bundle = KatalogBundle(
                lieferanten=[BundleLieferant(code="LIEF_DOPPEL", name="Doppel-Test")],
                baustoffe=[
                    Baustoff(
                        code="B_DOPPEL",
                        name="Doppel-Baustoff",
                        rohdichte_t_pro_m3=Decimal("2.4"),
                        einheit="t",
                    )
                ],
                preise=[
                    # Later-first on purpose: activation must not depend on list/insert order.
                    BundlePreis(
                        lieferant_code="LIEF_DOPPEL",
                        baustoff_code="B_DOPPEL",
                        preis_eur_pro_t=Decimal("20.00"),
                        gueltig_ab=date(2026, 9, 1),
                    ),
                    BundlePreis(
                        lieferant_code="LIEF_DOPPEL",
                        baustoff_code="B_DOPPEL",
                        preis_eur_pro_t=Decimal("15.00"),
                        gueltig_ab=date(2026, 8, 1),
                    ),
                ],
            )
            await service.bundle_aktivieren(await service.entwurf_speichern(bundle, benutzer="t"))

            async with engine.connect() as conn:
                preise = await KatalogRepository(conn).preise()
            paar = [
                p for p in preise
                if p.lieferant_code == "LIEF_DOPPEL" and p.baustoff_code == "B_DOPPEL"
            ]
            offen = [p for p in paar if p.gueltig_bis is None]
            assert len(paar) == 2
            assert len(offen) == 1 and offen[0].gueltig_ab == date(2026, 9, 1)
            august = next(p for p in paar if p.gueltig_ab == date(2026, 8, 1))
            assert august.gueltig_bis == date(2026, 8, 31)

            # Unambiguous resolution on both sides of the boundary.
            lief = m_lief.LIEFERANTEN["LIEF_DOPPEL"]
            assert lief.preis_fuer("B_DOPPEL", date(2026, 8, 15)) == Decimal("15.00")
            assert lief.preis_fuer("B_DOPPEL", date(2026, 10, 1)) == Decimal("20.00")
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()


async def test_bundle_zustand_uebergaenge(engine: AsyncEngine) -> None:
    """§6: entwurf → offen; aktiv → aktiviert; discarded → verworfen (rows never in force);
    activated and later superseded → geschlossen (rows archiviert)."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            buid = await service.entwurf_speichern(_neues_rezept(), benutzer="t")
            offen = await service.bundle_zustand(buid)
            assert offen.zustand == BundleZustand.OFFEN and offen.zeilen

            await service.bundle_aktivieren(buid)
            aktiviert = await service.bundle_zustand(buid)
            assert aktiviert.zustand == BundleZustand.AKTIVIERT

            verworfen_uuid = await service.entwurf_speichern(_rate_entwurf(), benutzer="t")
            await service.bundle_verwerfen(verworfen_uuid)
            verworfen = await service.bundle_zustand(verworfen_uuid)
            assert verworfen.zustand == BundleZustand.VERWORFEN
            assert all(z.status == KatalogStatus.VERWORFEN for z in verworfen.zeilen)

            # Re-activating the same keys supersedes the first bundle's rows.
            nachfolger = await service.entwurf_speichern(_neues_rezept(), benutzer="t")
            await service.bundle_aktivieren(nachfolger)
            geschlossen = await service.bundle_zustand(buid)
            assert geschlossen.zustand == BundleZustand.GESCHLOSSEN
            assert all(z.status == KatalogStatus.ARCHIVIERT for z in geschlossen.zeilen)
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()


async def test_versionen_liefert_scd2_zeitachse(engine: AsyncEngine) -> None:
    """The history endpoint's backing method: after activating a recipe and then superseding it,
    `versionen` returns every version of the key oldest-first (the Katalog UI's Versionshistorie)."""
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            # A seeded key has exactly one active version.
            eine = await service.versionen(KatalogEntitaet.FORMELN, "F_STUNDEN")
            assert [z.version for z in eine] == [1]
            assert eine[0].status == KatalogStatus.AKTIV

            # Activate, then supersede the same Leistung → two versions, the first archived.
            await service.bundle_aktivieren(await service.entwurf_speichern(_neues_rezept(), benutzer="t"))
            await service.bundle_aktivieren(await service.entwurf_speichern(_neues_rezept(), benutzer="t"))
            zwei = await service.versionen(KatalogEntitaet.LEISTUNGEN, "L_KATALOG_TEST")
            assert [z.version for z in zwei] == [1, 2]
            assert zwei[0].status == KatalogStatus.ARCHIVIERT and zwei[1].status == KatalogStatus.AKTIV
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
