"""Per-tool tests for the catalog write tools W1–W17 (§10.1).

Each tool is invoked the way the agent would (`ainvoke` a tool_call) against the seeded catalog; the
returned draft envelope and the persisted draft rows are asserted: draft status/bundle_uuid, delta
supersede preserving untouched fields, the diff, and that a validation failure persists nothing. The
tools never activate — only drafts are written, so the module seeds once and clears at teardown.
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
from shared.services.katalog.werkzeuge import katalog_werkzeuge
from shared.services.katalog.werkzeuge_schreiben import katalog_schreib_werkzeuge

from scripts.seed.seed_katalog import seed_katalog


@pytest_asyncio.fixture(scope="module")
async def schreib(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncEngine, dict[str, BaseTool]]]:
    async with engine.begin() as conn:
        repo = KatalogRepository(conn)
        await repo.alles_leeren()
        await seed_katalog(repo)
    tools = {t.name: t for t in katalog_schreib_werkzeuge(engine)}
    try:
        yield engine, tools
    finally:
        async with engine.begin() as conn:
            await KatalogRepository(conn).alles_leeren()


async def _call(tools: dict[str, BaseTool], werkzeug: str, /, **args: Any) -> dict[str, Any]:
    msg = await tools[werkzeug].ainvoke(
        {"type": "tool_call", "name": werkzeug, "args": args, "id": "c"}
    )
    return msg.artifact  # type: ignore[attr-defined]


async def _aktive(engine: AsyncEngine, entitaet: KatalogEntitaet) -> list:
    async with engine.connect() as conn:
        return await KatalogRepository(conn).aktive(entitaet)


async def _nach_bundle(engine: AsyncEngine, bundle_uuid: str) -> dict:
    async with engine.connect() as conn:
        return await KatalogRepository(conn).nach_bundle(UUID(bundle_uuid))


# --- Formeln & Variablen (W8–W12) ------------------------------------------------------------- #
async def test_w8_neue_basisformel(schreib) -> None:
    engine, tools = schreib
    # A genuinely NEW shape (Grundbetrag + mengenabhängiger Zuschlag) — not isomorphic to any base.
    art = await _call(
        tools, "neue_formel", name="F_TEST_GRUNDZUSCHLAG",
        ausdruck="grundbetrag + zuschlag * menge", einheit="€",
        beschreibung="Grundbetrag plus mengenabhängiger Zuschlag.",
        parameter=[{"name": "grundbetrag", "einheit": "€", "beschreibung": "Fixer Grundbetrag."},
                   {"name": "zuschlag", "einheit": "€/t", "beschreibung": "Zuschlag je Tonne."},
                   {"name": "menge", "einheit": "t", "beschreibung": "Bezugsmenge."}],
    )
    assert art["bundle_uuid"] and art["aktion"] == "neu"
    assert art["entwurf"]["latex"]  # real math on the card
    assert {p["name"] for p in art["entwurf"]["parameter"]} == {"grundbetrag", "zuschlag", "menge"}
    gruppen = await _nach_bundle(engine, art["bundle_uuid"])
    assert gruppen[KatalogEntitaet.FORMELN][0].status == KatalogStatus.ENTWURF
    # Formulas are no longer variables — no FORMEL-gruppe variable rides along.
    assert KatalogEntitaet.VARIABLEN not in gruppen


async def test_w8_isomorphe_formel_abgelehnt(schreib) -> None:
    """Structural dedup (§4): a candidate formula isomorphic to a base formula (here `a·b` ≡
    F_KOSTEN_SATZ / F_VOLUMEN_FLAECHE / F_MENGE_ANSATZ) is rejected — instantiate, don't mint."""
    _, tools = schreib
    art = await _call(
        tools, "neue_formel", name="F_TEST_FLAECHE", ausdruck="laenge * breite", einheit="m2",
        beschreibung="Rechteckfläche.",
        parameter=[{"name": "laenge", "einheit": "m", "beschreibung": "Länge."},
                   {"name": "breite", "einheit": "m", "beschreibung": "Breite."}],
    )
    assert art.get("bundle_uuid") is None
    assert any("strukturell identisch" in f and "instanziieren" in f for f in art["bericht"]["fehler"])


async def test_w8_unbekannte_funktion_persistiert_nichts(schreib) -> None:
    _, tools = schreib
    art = await _call(
        tools, "neue_formel", name="F_BAD", ausdruck="interpoliere(x)", einheit="€",
        beschreibung="Kaputt.", parameter=[{"name": "x", "beschreibung": "irgendwas"}],
    )
    assert art.get("bundle_uuid") is None
    assert any("unbekannte Funktion" in f and "round" in f for f in art["bericht"]["fehler"])


async def test_w9_aendere_formel_diff(schreib) -> None:
    engine, tools = schreib
    formeln = await _aktive(engine, KatalogEntitaet.FORMELN)
    ziel = next(f for f in formeln if f.schluessel == "F_KOSTEN_SATZ")
    art = await _call(tools, "aendere_formel", name="F_KOSTEN_SATZ", ausdruck=ziel.payload["ausdruck"] + " * 1")
    assert art["bundle_uuid"] and art["aktion"] == "aenderung"
    d = next(x for x in art["diff"] if x["feld"] == "ausdruck")
    assert d["alt"] == ziel.payload["ausdruck"] and d["neu"].endswith("* 1")


async def test_w10_neue_stammdaten_variable(schreib) -> None:
    engine, tools = schreib
    art = await _call(
        tools, "neue_stammdaten_variable", name="lohn_lg4_eur", bezeichnung="Lohngruppe 4",
        wert=24.80, einheit="€/h", beschreibung="Mittellohn Lohngruppe 4 je Stunde; speist den "
        "stundenlohn-Parameter von F_LOHN.",
    )
    assert art["bundle_uuid"] and art["entwurf"]["wert"] == "24.8"
    gruppen = await _nach_bundle(engine, art["bundle_uuid"])
    var = gruppen[KatalogEntitaet.VARIABLEN][0]
    assert var.status == KatalogStatus.ENTWURF and var.payload["gruppe"] == "stammdaten"


async def test_w10_ohne_beschreibung_persistiert_nichts(schreib) -> None:
    """Mandatory-prose enforcement (§2.6): a stammdaten variable without beschreibung is rejected."""
    _, tools = schreib
    art = await _call(
        tools, "neue_stammdaten_variable", name="lohn_ohne_prosa", bezeichnung="Ohne Prosa",
        wert=1.0, einheit="€/h", beschreibung="   ",
    )
    assert art.get("bundle_uuid") is None
    assert any("lohn_ohne_prosa" in f and "beschreibung fehlt" in f for f in art["bericht"]["fehler"])


async def test_w11_aendere_stammdaten_wert(schreib) -> None:
    engine, tools = schreib
    art = await _call(tools, "aendere_stammdaten_wert", name="kraftstoffpreis_eur_pro_l", wert=1.89)
    assert art["bundle_uuid"]
    d = art["diff"][0]
    assert d["feld"] == "wert" and d["neu"] == "1.89"
    # The where-used blast radius rides the envelope (many Vorgänge bind the fuel price).
    assert art["entwurf"]["verwendung"]["vorgaenge"]
    gruppen = await _nach_bundle(engine, art["bundle_uuid"])
    assert gruppen[KatalogEntitaet.VARIABLEN][0].status == KatalogStatus.ENTWURF


async def test_w12_neue_kontext_variable_kaskade(schreib) -> None:
    _, tools = schreib
    art = await _call(
        tools, "neue_kontext_variable", name="test_kontext_x", bezeichnung="Test-Kontext",
        beschreibung="Test-Kontextwert in cm; situativer Eingabewert.",
        einheit="cm", llm_hinweis="Aus dem Gutachten bestimmen.", default_wert=5.0,
    )
    assert art["bundle_uuid"]
    assert art["entwurf"]["kaskade"] == ["langtext", "rag", "hitl", "konstante"]


# --- Baustoffe / Lieferanten / Preise (W1–W7) ------------------------------------------------- #
async def test_w1_neuer_baustoff(schreib) -> None:
    engine, tools = schreib
    art = await _call(
        tools, "neuer_baustoff", code="AC_16_B_S_TEST", name="AC 16 B S",
        rohdichte_t_pro_m3=2.4, kategorie="Asphaltmischgut",
    )
    assert art["bundle_uuid"]
    gruppen = await _nach_bundle(engine, art["bundle_uuid"])
    assert gruppen[KatalogEntitaet.BAUSTOFFE][0].status == KatalogStatus.ENTWURF


async def test_w2_aendere_baustoff_erhaelt_unberuehrte_felder(schreib) -> None:
    engine, tools = schreib
    b = (await _aktive(engine, KatalogEntitaet.BAUSTOFFE))[0]
    art = await _call(tools, "aendere_baustoff", code=b.schluessel, aenderungen={"basispreis_eur_pro_t": 16.20})
    assert art["bundle_uuid"]
    assert art["entwurf"]["name"] == b.payload["name"]  # untouched field preserved
    assert art["entwurf"]["basispreis_eur_pro_t"] == "16.2"
    assert any(d["feld"] == "basispreis_eur_pro_t" for d in art["diff"])


async def test_w2_r9_unbekanntes_feld(schreib) -> None:
    engine, tools = schreib
    b = (await _aktive(engine, KatalogEntitaet.BAUSTOFFE))[0]
    art = await _call(tools, "aendere_baustoff", code=b.schluessel, aenderungen={"quatsch": 1})
    assert art.get("bundle_uuid") is None
    assert any("quatsch" in f for f in art["bericht"]["fehler"])


async def test_w5_neuer_lieferant(schreib) -> None:
    engine, tools = schreib
    art = await _call(
        tools, "neuer_lieferant", code="LIEF_TEST_W5", name="Harzland Schotter",
        standort="Goslar", breitengrad=51.9, laengengrad=10.4,
    )
    assert art["bundle_uuid"] and art["entwurf"]["standort"] == "Goslar"
    gruppen = await _nach_bundle(engine, art["bundle_uuid"])
    assert gruppen[KatalogEntitaet.LIEFERANTEN][0].status == KatalogStatus.ENTWURF


async def test_w6_aendere_lieferant(schreib) -> None:
    engine, tools = schreib
    lf = (await _aktive(engine, KatalogEntitaet.LIEFERANTEN))[0]
    art = await _call(tools, "aendere_lieferant", code=lf.schluessel, aenderungen={"standort": "Neuort"})
    assert art["bundle_uuid"] and art["entwurf"]["standort"] == "Neuort"
    assert art["entwurf"]["name"] == lf.payload["name"]


async def test_w7_neuer_preis_mit_closeout_warnung(schreib) -> None:
    engine, tools = schreib
    async with engine.connect() as conn:
        preise = await KatalogRepository(conn).preise()
    offen = next(p for p in preise if p.gueltig_bis is None)
    art = await _call(
        tools, "neuer_preis", lieferant_code=offen.lieferant_code,
        baustoff_code=offen.baustoff_code, preis_eur_pro_t=99.0, gueltig_ab="2027-01-01",
    )
    assert art["bundle_uuid"] and art["warnungen"]  # predecessor close-out warned
    async with engine.connect() as conn:
        drafts = await KatalogRepository(conn).preise_nach_bundle(UUID(art["bundle_uuid"]))
    assert len(drafts) == 1
    assert drafts[0].status == KatalogStatus.ENTWURF and drafts[0].preis_eur_pro_t == Decimal("99")


async def test_w7_preis_unbekannter_lieferant_persistiert_nichts(schreib) -> None:
    _, tools = schreib
    art = await _call(
        tools, "neuer_preis", lieferant_code="LIEF_GHOST", baustoff_code="B_GHOST",
        preis_eur_pro_t=10.0,
    )
    assert art.get("bundle_uuid") is None
    assert any("unbekannter Lieferant" in f for f in art["bericht"]["fehler"])


# --- Maschinen (W3/W4) ------------------------------------------------------------------------ #
async def test_w3_neue_maschine(schreib) -> None:
    engine, tools = schreib
    aa = (await _aktive(engine, KatalogEntitaet.AUSFUEHRUNGSARTEN))[0].schluessel
    ba = (await _aktive(engine, KatalogEntitaet.BETRIEBSARTEN))[0].schluessel
    art = await _call(
        tools, "neue_maschine", code="M_TEST_W3", hersteller="Wirtgen", modell="W 210 Fi",
        ausfuehrungsart_code=aa,
        eigenschaften={"stundensatz_eur": {"wert": 340, "einheit": "€/h"}},
        leistungsprofile=[{"betriebsart_code": ba, "leistung": 950, "einheit": "m2/h"}],
    )
    assert art["bundle_uuid"]
    assert art["entwurf"]["eigenschaften"]["stundensatz_eur"]["wert"] == "340"


async def test_w4_aendere_maschine_geraeteklasse_move_und_merge(schreib) -> None:
    engine, tools = schreib
    m = (await _aktive(engine, KatalogEntitaet.MASCHINEN))[0]
    aas = await _aktive(engine, KatalogEntitaet.AUSFUEHRUNGSARTEN)
    ziel = next(a.schluessel for a in aas if a.schluessel != m.payload["ausfuehrungsart_code"])
    art = await _call(tools, "aendere_maschine", code=m.schluessel, aenderungen={"ausfuehrungsart_code": ziel})
    assert art["bundle_uuid"]
    assert art["entwurf"]["ausfuehrungsart_code"] == ziel
    # eigenschaften are merged, not dropped: the original keys survive.
    assert set(m.payload["eigenschaften"]).issubset(set(art["entwurf"]["eigenschaften"]))


# --- Taxonomien & Mapping (W13–W16) ----------------------------------------------------------- #
async def test_w13_w14_w15_taxonomien(schreib) -> None:
    engine, tools = schreib
    a = await _call(tools, "neue_ausfuehrungsart", code="AA_TEST_W13", name="Test-Geräteklasse")
    assert a["bundle_uuid"]
    k = await _call(tools, "neue_betriebskategorie", code="BK_TEST_W14", bezeichnung="Test-Kategorie")
    assert k["bundle_uuid"]
    b = await _call(
        tools, "neue_betriebsart", code="BA_TEST_W15", bezeichnung="Test-Betriebsart",
        kategorie_code="BK_TEST_W14",
    )
    # The Kategorie is in-bundle-of-a-different-bundle → not active yet, so this must fail R4.
    assert b.get("bundle_uuid") is None
    # With an existing active Kategorie it validates.
    kat = (await _aktive(engine, KatalogEntitaet.BETRIEBSKATEGORIEN))[0].schluessel
    b2 = await _call(
        tools, "neue_betriebsart", code="BA_TEST_W15b", bezeichnung="Test", kategorie_code=kat
    )
    assert b2["bundle_uuid"]


async def test_w16_bauverfahren_zu_leistung_reihenfolge(schreib) -> None:
    engine, tools = schreib
    mappings = await _aktive(engine, KatalogEntitaet.LEISTUNG_BAUVERFAHREN)
    row = next((r for r in mappings if len(r.payload["bauverfahren_codes"]) >= 2), mappings[0])
    alt = row.payload["bauverfahren_codes"]
    neu = list(reversed(alt))
    art = await _call(tools, "bauverfahren_zu_leistung", leistung_code=row.schluessel, bauverfahren_codes=neu)
    assert art["bundle_uuid"]
    assert art["diff"][0]["alt"] == alt and art["diff"][0]["neu"] == neu


# --- Lifecycle (W17) -------------------------------------------------------------------------- #
async def test_w17_entwurf_verwerfen(schreib) -> None:
    _, tools = schreib
    entwurf = await _call(tools, "neue_ausfuehrungsart", code="AA_VERWERF_W17", name="Verwerf")
    buid = entwurf["bundle_uuid"]
    verworfen = await _call(tools, "entwurf_verwerfen", bundle_uuid=buid)
    assert verworfen["bundle_uuid"] == buid and verworfen["entwurf"]["verworfen"] is True
    # Discarding a bundle with no open drafts errors.
    wieder = await _call(tools, "entwurf_verwerfen", bundle_uuid=buid)
    assert wieder.get("bundle_uuid") is None and wieder["bericht"]["fehler"]


async def test_w17_ungueltige_uuid(schreib) -> None:
    _, tools = schreib
    art = await _call(tools, "entwurf_verwerfen", bundle_uuid="kein-uuid")
    assert art.get("bundle_uuid") is None and art["bericht"]["fehler"]


async def test_t33_offener_entwurf_erscheint_in_liste(schreib) -> None:
    engine, tools = schreib
    art = await _call(tools, "neue_ausfuehrungsart", code="AA_LISTE_T33", name="Liste")
    lese_tools = {t.name: t for t in katalog_werkzeuge(engine)}
    msg = await lese_tools["liste_entwuerfe"].ainvoke(
        {"type": "tool_call", "name": "liste_entwuerfe", "args": {}, "id": "c"}
    )
    assert art["bundle_uuid"] in {e["bundle_uuid"] for e in msg.artifact["eintraege"]}
