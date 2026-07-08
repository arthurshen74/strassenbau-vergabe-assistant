"""Per-behaviour tests for the W18 recipe-compiler tool (Phase 3, §3–§4).

The tool is invoked the way the agent would (`ainvoke` a tool_call) against the seeded catalog:
the happy path persists a complete recipe as ONE draft bundle (envelope carries LaTeX, the
justification lists and warnings); transport/validation/coverage failures persist nothing and
report every problem for agentic repair; near-duplicate warnings fire on minted lookalikes but
never block. The e2e test activates the saved St-recipe and calculates a Stück position (D4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest_asyncio
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import KatalogEntitaet, KatalogStatus
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.model import AufloesungsMethode
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.store import KATALOG, kalkuliere
from shared.services.katalog.service import KatalogService
from shared.services.katalog.werkzeuge_rezept import katalog_rezept_werkzeuge

from scripts.check_katalog_parity import zustand_sichern
from scripts.seed.seed_katalog import seed_katalog


@pytest_asyncio.fixture(scope="module")
async def rezept(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncEngine, BaseTool]]:
    async with engine.begin() as conn:
        repo = KatalogRepository(conn)
        await repo.alles_leeren()
        await seed_katalog(repo)
    (werkzeug,) = katalog_rezept_werkzeuge(engine)
    try:
        yield engine, werkzeug
    finally:
        async with engine.begin() as conn:
            await KatalogRepository(conn).alles_leeren()


async def _call(werkzeug: BaseTool, **args: Any) -> dict[str, Any]:
    msg = await werkzeug.ainvoke(
        {"type": "tool_call", "name": werkzeug.name, "args": args, "id": "c"}
    )
    return msg.artifact  # type: ignore[attr-defined]


async def _erste_aa(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        return (await KatalogRepository(conn).aktive(KatalogEntitaet.AUSFUEHRUNGSARTEN))[0].schluessel


async def _offene_bundles(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return len(await KatalogRepository(conn).offene_bundles())


def _kappen_rezept(aa_code: str) -> dict[str, Any]:
    """An R2-style Stück recipe: hand work over `anzahl_st` (D4). The redesign shape — the Vorgang's
    Rechnung INSTANTIATES seeded base formulas (F_STUNDEN, F_LOHN, F_KOSTEN_SATZ); only the two
    company-knowledge rates are minted. No recipe-specific formulas."""
    return {
        "leistungen": [{"code": "L_TEST_KAPPE", "name": "Schieberkappe regulieren", "einheit": "St"}],
        "bauverfahren": [{"code": "BV_TEST_KAPPE", "name": "Kappe von Hand regulieren",
                          "vorgang_codes": ["V_TEST_KAPPE"]}],
        "vorgaenge": [{
            "code": "V_TEST_KAPPE", "name": "Schieberkappe freilegen und auf Höhe setzen",
            "ausfuehrungsart_code": aa_code,
            "rechnung": {
                "instanzen": {
                    "arbeitszeit": {"formel": "F_STUNDEN", "bindung": {
                        "menge": "kontext.anzahl_st", "leistung": "stammdaten.test_kappen_pro_h"}},
                },
                "kosten": {
                    "Lohn": [{"formel": "F_LOHN", "bindung": {
                        "stunden": "formel.arbeitszeit", "stundenlohn": "stammdaten.stundenlohn_eur",
                        "kolonne": "kontext.anzahl_arbeiter"}}],
                    "Material": [{"formel": "F_KOSTEN_SATZ", "bindung": {
                        "menge": "kontext.anzahl_st", "satz": "stammdaten.test_kleinmaterial_eur_pro_st"}}],
                },
            },
        }],
        "variablen": [
            {"name": "test_kappen_pro_h", "gruppe": "stammdaten",
             "bezeichnung": "Regulier-Leistung Schieberkappen", "wert": 4, "einheit": "St/h",
             "beschreibung": "Anzahl regulierter Schieberkappen je Stunde; leistung-Parameter von "
                             "F_STUNDEN für V_TEST_KAPPE."},
            {"name": "test_kleinmaterial_eur_pro_st", "gruppe": "stammdaten",
             "bezeichnung": "Mörtel und Kleinmaterial je Kappe", "wert": 5, "einheit": "€/St",
             "beschreibung": "Mörtel-/Kleinmaterialkosten je Kappe; satz-Parameter der "
                             "F_KOSTEN_SATZ-Materialzeile."},
        ],
        "leistung_bauverfahren": {"L_TEST_KAPPE": ["BV_TEST_KAPPE"]},
    }


def _kappen_wiederverwendung(aa_code: str) -> list[dict[str, str]]:
    return [
        {"code": "F_STUNDEN", "warum": "Basisformel Arbeitszeit = Menge / Leistung"},
        {"code": "F_LOHN", "warum": "Basisformel Lohnkosten"},
        {"code": "F_KOSTEN_SATZ", "warum": "Basisformel Menge × Satz"},
        {"code": "anzahl_st", "warum": "St-Geometrie aus der LV-Menge"},
        {"code": "anzahl_arbeiter", "warum": "Kolonnenstärke, Standard 2"},
        {"code": "stundenlohn_eur", "warum": "Stammdaten-Lohnsatz"},
        {"code": aa_code, "warum": "vorhandene Geräteklasse"},
    ]


_KAPPEN_NEU = [
    {"code": "L_TEST_KAPPE", "warum_nicht_vorhanden": "keine Leistung für Schieberkappen"},
    {"code": "BV_TEST_KAPPE", "warum_nicht_vorhanden": "neues Verfahren"},
    {"code": "V_TEST_KAPPE", "warum_nicht_vorhanden": "neuer Arbeitsschritt"},
    {"code": "test_kappen_pro_h", "warum_nicht_vorhanden": "neuer Leistungsansatz"},
    {"code": "test_kleinmaterial_eur_pro_st", "warum_nicht_vorhanden": "neuer Satz"},
]


# --- Happy path ------------------------------------------------------------------------------- #
async def test_w18_rezept_speichert_einen_bundle(rezept) -> None:
    engine, werkzeug = rezept
    aa = await _erste_aa(engine)
    art = await _call(
        werkzeug, bundle=_kappen_rezept(aa),
        wiederverwendung=_kappen_wiederverwendung(aa), neu=_KAPPEN_NEU,
    )
    assert art["bericht"]["fehler"] == []
    assert art["bundle_uuid"] and art["aktion"] == "rezept" and art["schluessel"] == "L_TEST_KAPPE"
    # Search-before-create: the recipe instantiates existing base formulas, mints none.
    assert art["entwurf"]["formeln"] == []
    assert {e["code"] for e in art["wiederverwendung"]} == {
        "F_STUNDEN", "F_LOHN", "F_KOSTEN_SATZ", "anzahl_st", "anzahl_arbeiter", "stundenlohn_eur", aa
    }
    assert len(art["neu"]) == len(_KAPPEN_NEU)
    # One draft bundle: every row entwurf; only the two minted rates are new VARIABLEN
    # (formulas are no longer variables, so none ride along), and no FORMELN row is minted.
    async with engine.connect() as conn:
        gruppen = await KatalogRepository(conn).nach_bundle(UUID(art["bundle_uuid"]))
    assert all(z.status == KatalogStatus.ENTWURF for zs in gruppen.values() for z in zs)
    assert {z.schluessel for z in gruppen[KatalogEntitaet.LEISTUNGEN]} == {"L_TEST_KAPPE"}
    assert {z.schluessel for z in gruppen[KatalogEntitaet.VARIABLEN]} == {
        "test_kappen_pro_h", "test_kleinmaterial_eur_pro_st",
    }
    assert KatalogEntitaet.FORMELN not in gruppen
    # Clean up the draft so later tests count open bundles from a known state.
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


async def test_w18_neue_basisformel_wird_gemuenzt(rezept) -> None:
    """Minting a genuinely new base formula: the declared parameter signature + prose ride the
    bundle and the envelope renders its LaTeX + parameters."""
    engine, werkzeug = rezept
    bundle = {
        "formeln": [{
            "name": "F_TEST_GRUNDZUSCHLAG", "ausdruck": "grundpreis + zuschlag * menge", "einheit": "€",
            "beschreibung": "Grundbetrag plus mengenabhängiger Zuschlag.",
            "parameter": [
                {"name": "grundpreis", "einheit": "€", "beschreibung": "Fixer Grundbetrag je Position."},
                {"name": "zuschlag", "einheit": "€/t", "beschreibung": "Zuschlag je Tonne."},
                {"name": "menge", "einheit": "t", "beschreibung": "Bezugsmenge."},
            ],
        }],
    }
    art = await _call(werkzeug, bundle=bundle, wiederverwendung=[],
                      neu=[{"code": "F_TEST_GRUNDZUSCHLAG", "warum_nicht_vorhanden": "neue Preisform"}])
    assert art["bericht"]["fehler"] == []
    (f,) = art["entwurf"]["formeln"]
    assert f["latex"] and {p["name"] for p in f["parameter"]} == {"grundpreis", "zuschlag", "menge"}
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


async def test_w18_kontext_variable_kaskade_serverseitig(rezept) -> None:
    engine, werkzeug = rezept
    bundle = {
        "variablen": [{"name": "test_ktx_tiefe", "gruppe": "kontext", "bezeichnung": "Testtiefe",
                       "einheit": "cm", "llm_hinweis": "Aus dem Langtext.", "default_wert": 3,
                       "beschreibung": "Test-Kontexttiefe in cm; situativer Eingabewert."}],
    }
    art = await _call(werkzeug, bundle=bundle, wiederverwendung=[],
                      neu=[{"code": "test_ktx_tiefe", "warum_nicht_vorhanden": "neu"}])
    assert art["bundle_uuid"]
    (var,) = art["entwurf"]["variablen"]
    assert var["kaskade"] == ["langtext", "rag", "hitl", "konstante"]
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


# --- Failure paths persist nothing ------------------------------------------------------------- #
async def test_w18_abdeckung_fehlende_begruendung(rezept) -> None:
    engine, werkzeug = rezept
    aa = await _erste_aa(engine)
    vorher = await _offene_bundles(engine)
    unvollstaendig = [e for e in _kappen_wiederverwendung(aa) if e["code"] != "stundenlohn_eur"]
    art = await _call(werkzeug, bundle=_kappen_rezept(aa),
                      wiederverwendung=unvollstaendig, neu=_KAPPEN_NEU)
    assert art.get("bundle_uuid") is None
    assert any("stundenlohn_eur" in f and "nicht begründet" in f for f in art["bericht"]["fehler"])
    assert await _offene_bundles(engine) == vorher


async def test_w18_abdeckung_beide_listen_und_falsches_neu(rezept) -> None:
    engine, werkzeug = rezept
    aa = await _erste_aa(engine)
    art = await _call(
        werkzeug, bundle=_kappen_rezept(aa),
        wiederverwendung=_kappen_wiederverwendung(aa),
        neu=_KAPPEN_NEU + [{"code": "anzahl_st", "warum_nicht_vorhanden": "doppelt"}],
    )
    assert art.get("bundle_uuid") is None
    assert any("beiden Listen" in f for f in art["bericht"]["fehler"])

    nur_referenziert = [e for e in _kappen_wiederverwendung(aa) if e["code"] != aa]
    art2 = await _call(
        werkzeug, bundle=_kappen_rezept(aa), wiederverwendung=nur_referenziert,
        neu=_KAPPEN_NEU + [{"code": aa, "warum_nicht_vorhanden": "falsch deklariert"}],
    )
    assert art2.get("bundle_uuid") is None
    assert any("nur referenziert" in f for f in art2["bericht"]["fehler"])


async def test_w18_validierungsfehler_gesammelt(rezept) -> None:
    engine, werkzeug = rezept
    vorher = await _offene_bundles(engine)
    bundle = {
        "formeln": [{"name": "test_bad", "ausdruck": "interpoliere(laenge_m)"}],
        "variablen": [{"name": "test_ohne_wert", "gruppe": "stammdaten", "bezeichnung": "kaputt"}],
    }
    art = await _call(werkzeug, bundle=bundle, wiederverwendung=[], neu=[])
    assert art.get("bundle_uuid") is None
    # Transport errors are collected across sections (the stammdaten `wert` is checked at build).
    assert any("test_ohne_wert" in f and "wert" in f for f in art["bericht"]["fehler"])
    assert await _offene_bundles(engine) == vorher

    art2 = await _call(werkzeug, bundle={"formeln": bundle["formeln"]}, wiederverwendung=[],
                       neu=[{"code": "test_bad", "warum_nicht_vorhanden": "test"}])
    assert art2.get("bundle_uuid") is None
    assert any("unbekannte Funktion" in f for f in art2["bericht"]["fehler"])


# --- Geometry warning (soft) -------------------------------------------------------------------- #
async def test_w18_fremde_geometrie_warnt_blockiert_nicht(rezept) -> None:
    engine, werkzeug = rezept
    aa = await _erste_aa(engine)
    bundle = _kappen_rezept(aa)
    # A St-billed recipe whose Arbeitszeit-Instanz binds volumen_m3 instead of the booked anzahl_st.
    bundle["vorgaenge"][0]["rechnung"]["instanzen"]["arbeitszeit"]["bindung"]["menge"] = "kontext.volumen_m3"
    art = await _call(
        werkzeug, bundle=bundle,
        wiederverwendung=_kappen_wiederverwendung(aa)
        + [{"code": "volumen_m3", "warum": "Test"}],
        neu=_KAPPEN_NEU,
    )
    assert art["bundle_uuid"]  # warnings never block
    assert any("volumen_m3" in w and "anzahl_st" in w for w in art["warnungen"])
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


async def test_w18_transitive_geometrie_ueber_wiederverwendeten_vorgang(rezept) -> None:
    """A t-billed recipe reusing the active m²-based V_FRAESEN chain member: the geometry walk
    must flag the foreign geometry the reused Vorgang transitively depends on."""
    engine, werkzeug = rezept
    bundle = {
        "leistungen": [{"code": "L_TEST_T_REUSE", "name": "Test t-Leistung", "einheit": "t"}],
        "bauverfahren": [{"code": "BV_TEST_T_REUSE", "name": "Test", "vorgang_codes": ["V_FRAESEN"]}],
        "leistung_bauverfahren": {"L_TEST_T_REUSE": ["BV_TEST_T_REUSE"]},
    }
    art = await _call(
        werkzeug, bundle=bundle,
        wiederverwendung=[{"code": "V_FRAESEN", "warum": "Test"}],
        neu=[{"code": "L_TEST_T_REUSE", "warum_nicht_vorhanden": "Test"},
             {"code": "BV_TEST_T_REUSE", "warum_nicht_vorhanden": "Test"}],
    )
    assert art["bundle_uuid"]  # warnings never block
    assert any("V_FRAESEN" in w and "Geometrie" in w for w in art["warnungen"])
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


# --- Near-duplicate warnings (soft) ------------------------------------------------------------ #
async def test_w18_dubletten_warnung_blockiert_nicht(rezept) -> None:
    engine, werkzeug = rezept
    bundle = {"vorgaenge": [{"code": "V_TEST_DUP", "name": "Asphalt fräsen"}]}
    art = await _call(werkzeug, bundle=bundle, wiederverwendung=[],
                      neu=[{"code": "V_TEST_DUP", "warum_nicht_vorhanden": "Test"}])
    assert art["bundle_uuid"]  # warnings never block
    assert any("V_FRAESEN" in w for w in art["warnungen"])
    await KatalogService(engine).bundle_verwerfen(UUID(art["bundle_uuid"]))


# --- e2e: activate the St recipe and calculate a Stück position (D4) --------------------------- #
async def test_w18_rezept_aktivieren_und_st_position_kalkulieren(engine: AsyncEngine) -> None:
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            (werkzeug,) = katalog_rezept_werkzeuge(engine)
            aa = await _erste_aa(engine)
            art = await _call(
                werkzeug, bundle=_kappen_rezept(aa),
                wiederverwendung=_kappen_wiederverwendung(aa), neu=_KAPPEN_NEU,
            )
            assert art["bundle_uuid"]
            await KatalogService(engine).bundle_aktivieren(UUID(art["bundle_uuid"]))

            # 8 Kappen: Lohn = 8/4 h × 2 Mann × Satz; Material = 8 × 5 €.
            ergebnis = kalkuliere(Position(oz="T-R2", leistung_key="L_TEST_KAPPE", menge=Decimal(8)))
            satz = next(
                s.konstante for s in KATALOG["stundenlohn_eur"].aufloesung
                if s.methode == AufloesungsMethode.KONSTANTE
            )
            erwartet = (Decimal(2) * 2 * satz + Decimal(40)).quantize(Decimal("0.01"))
            assert ergebnis["einheit"] == "St" and ergebnis["ekt_eur"] == erwartet
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()
