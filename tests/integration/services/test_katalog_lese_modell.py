"""Per-tool tests for the Katalog read layer (§10.1): shape + one relationship assertion each,
against the seeded fixture catalog. Also the truncation guard (§10.3): treffer_gesamt on a >limit
listing. The catalog is seeded once per module (read-only tools share one LeseModell)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import KatalogEntitaet
from shared.repositories.katalog import KatalogRepository
from shared.services.katalog.lese_modell import LeseModell

from scripts.seed.seed_katalog import seed_katalog


@pytest_asyncio.fixture(scope="module")
async def lese(engine: AsyncEngine) -> AsyncIterator[LeseModell]:
    async with engine.begin() as conn:
        repo = KatalogRepository(conn)
        await repo.alles_leeren()
        await seed_katalog(repo)
    try:
        async with engine.connect() as conn:
            yield LeseModell(conn)
    finally:
        async with engine.begin() as conn:
            await KatalogRepository(conn).alles_leeren()


# --- Meta and search --------------------------------------------------------- #
async def test_t1_katalog_uebersicht(lese: LeseModell) -> None:
    u = await lese.katalog_uebersicht()
    assert u["entitaeten"]["leistungen"] > 0
    # T1 reads the katalog_stand row: version 1 at seed, benutzer "seed", last-touched timestamp.
    assert u["stand"]["version"] == 1
    assert u["stand"]["benutzer"] == "seed"
    assert "aktualisiert_am" in u["stand"]
    assert u["offene_entwuerfe"] == 0


async def test_t2_suche_katalog(lese: LeseModell) -> None:
    treffer = (await lese.suche_katalog("AC 22"))["eintraege"]
    assert any(t["schluessel"] == "ASPHALT_AC22TS" for t in treffer)
    assert all({"entitaet", "schluessel", "name", "score"} <= t.keys() for t in treffer)


async def test_t3_zeige_dsl_funktionen(lese: LeseModell) -> None:
    dsl = await lese.zeige_dsl_funktionen()
    namen = {f["name"] for f in dsl["funktionen"]}
    assert {"ceil", "max", "floor"} <= namen
    assert any(o["symbol"] == "**" for o in dsl["operatoren"])


# --- Leistungen -------------------------------------------------------------- #
async def test_t4_liste_leistungen(lese: LeseModell) -> None:
    liste = await lese.liste_leistungen()
    fss = next(e for e in liste["eintraege"] if e["code"] == "L_FSS")
    assert fss["bauverfahren_kandidaten"] == 2
    assert liste["treffer_gesamt"] >= len(liste["eintraege"])


async def test_t5_zeige_leistung(lese: LeseModell) -> None:
    l = await lese.zeige_leistung("L_FSS")
    assert [b["code"] for b in l["bauverfahren"]] == ["BV_FSS_GRADER", "BV_FSS_FERTIGER"]
    assert l["bauverfahren"][0]["standard"] is True


# --- Bauverfahren ------------------------------------------------------------ #
async def test_t6_liste_bauverfahren(lese: LeseModell) -> None:
    liste = await lese.liste_bauverfahren()
    bv = next(e for e in liste["eintraege"] if e["code"] == "BV_FSS_GRADER")
    assert bv["vorgaenge"] > 0 and bv["genutzt_von_leistungen"] >= 1


async def test_t7_zeige_bauverfahren(lese: LeseModell) -> None:
    bv = await lese.zeige_bauverfahren("BV_FSS_GRADER")
    assert bv["vorgaenge"], "the Vorgang chain must not be empty"
    assert "L_FSS" in bv["genutzt_von_leistungen"]


async def test_t8_finde_bauverfahren_mit_vorgang(lese: LeseModell) -> None:
    kette = (await lese.zeige_bauverfahren("BV_FSS_GRADER"))["vorgaenge"]
    erster = kette[0]["code"]
    fund = await lese.finde_bauverfahren_mit_vorgang(erster)
    treffer = next(t for t in fund["bauverfahren"] if t["code"] == "BV_FSS_GRADER")
    assert treffer["position"] == 1


# --- Vorgänge ---------------------------------------------------------------- #
async def test_t9_liste_vorgaenge_facet_filter(lese: LeseModell) -> None:
    liste = await lese.liste_vorgaenge(ausfuehrungsart_code="AA_KALTFRAESE")
    assert liste["eintraege"]
    assert all(e["ausfuehrungsart_code"] == "AA_KALTFRAESE" for e in liste["eintraege"])
    assert any(e["code"] == "V_FRAESEN" for e in liste["eintraege"])


async def test_t10_zeige_vorgang(lese: LeseModell) -> None:
    v = await lese.zeige_vorgang("V_FRAESEN")
    assert v["ausfuehrungsart"]["code"] == "AA_KALTFRAESE"
    assert v["kostenvariablen"] and all("variable" in k for k in v["kostenvariablen"])
    assert v["enthalten_in_bauverfahren"]


# --- Ausführungsarten / Betriebsarten / -kategorien -------------------------- #
async def test_t11_liste_ausfuehrungsarten(lese: LeseModell) -> None:
    liste = await lese.liste_ausfuehrungsarten()
    aa = next(e for e in liste["eintraege"] if e["code"] == "AA_KALTFRAESE")
    assert aa["maschinen"] >= 1 and aa["vorgaenge"] >= 1


async def test_t12_zeige_ausfuehrungsart(lese: LeseModell) -> None:
    aa = await lese.zeige_ausfuehrungsart("AA_KALTFRAESE")
    assert aa["maschinen"], "machines filling the slot"
    assert any(v["code"] == "V_FRAESEN" for v in aa["vorgaenge"])


async def test_t13_liste_betriebskategorien(lese: LeseModell) -> None:
    liste = await lese.liste_betriebskategorien()
    fraesen = next(e for e in liste["eintraege"] if e["code"] == "fraesen")
    assert fraesen["betriebsarten"] >= 1


async def test_t14_liste_betriebsarten_kategorie_filter(lese: LeseModell) -> None:
    liste = await lese.liste_betriebsarten(kategorie_code="fraesen")
    assert liste["eintraege"]
    assert all(e["kategorie_code"] == "fraesen" for e in liste["eintraege"])


async def test_t15_zeige_betriebsart(lese: LeseModell) -> None:
    code = (await lese.liste_betriebsarten(kategorie_code="fraesen"))["eintraege"][0]["code"]
    bt = await lese.zeige_betriebsart(code)
    assert bt["kategorie_code"] == "fraesen"
    assert "maschinen" in bt and "vorgaenge" in bt


# --- Maschinen --------------------------------------------------------------- #
async def test_t16_liste_maschinen_facet_filter(lese: LeseModell) -> None:
    liste = await lese.liste_maschinen(ausfuehrungsart_code="AA_KALTFRAESE")
    assert liste["eintraege"]
    assert all(e["ausfuehrungsart_code"] == "AA_KALTFRAESE" for e in liste["eintraege"])


async def test_t17_zeige_maschine(lese: LeseModell) -> None:
    code = (await lese.liste_maschinen(ausfuehrungsart_code="AA_KALTFRAESE"))["eintraege"][0]["code"]
    m = await lese.zeige_maschine(code)
    assert m["ausfuehrungsart"]["code"] == "AA_KALTFRAESE"
    assert m["eigenschaften"] and m["leistungsprofile"]


# --- Baustoffe --------------------------------------------------------------- #
async def test_t18_liste_baustoffe(lese: LeseModell) -> None:
    liste = await lese.liste_baustoffe(filter_text="AC 22")
    assert any(e["code"] == "ASPHALT_AC22TS" for e in liste["eintraege"])


async def test_t19_liste_baustoff_kategorien(lese: LeseModell) -> None:
    liste = await lese.liste_baustoff_kategorien()
    assert liste["eintraege"] and all("baustoffe" in e for e in liste["eintraege"])
    assert sum(e["baustoffe"] for e in liste["eintraege"]) >= len(liste["eintraege"])


async def test_t20_zeige_baustoff(lese: LeseModell) -> None:
    b = await lese.zeige_baustoff("ASPHALT_AC22TS")
    assert b["name"] == "Asphalttragschicht AC 22 T S"
    assert b["lieferanten_anzahl"] >= 1


async def test_t21_finde_lieferanten_fuer_baustoff(lese: LeseModell) -> None:
    # The canonical question: "Welche Lieferanten können AC 22 T S liefern?"
    fund = await lese.finde_lieferanten_fuer_baustoff("ASPHALT_AC22TS")
    lieferanten = fund["lieferanten"]
    assert lieferanten, "at least one supplier must carry AC 22 T S"
    preise = [float(l["werkspreis_eur_pro_t"]) for l in lieferanten]
    assert preise == sorted(preise), "sorted by ex-works price ascending"
    assert all({"lieferant_code", "name", "werkspreis_eur_pro_t"} <= l.keys() for l in lieferanten)


# --- Lieferanten & Preise ---------------------------------------------------- #
async def test_t22_liste_lieferanten(lese: LeseModell) -> None:
    liste = await lese.liste_lieferanten()
    assert liste["eintraege"]
    assert any(e["baustoffe_im_sortiment"] > 0 for e in liste["eintraege"])


async def test_t23_zeige_lieferant(lese: LeseModell) -> None:
    code = (await lese.finde_lieferanten_fuer_baustoff("ASPHALT_AC22TS"))["lieferanten"][0]["lieferant_code"]
    lief = await lese.zeige_lieferant(code)
    assert lief["sortiment"] and all("kategorie" in s for s in lief["sortiment"])


async def test_t24_zeige_preise(lese: LeseModell) -> None:
    preise = await lese.zeige_preise(baustoff_code="ASPHALT_AC22TS")
    assert preise["eintraege"]
    assert all(e["baustoff_code"] == "ASPHALT_AC22TS" and "gueltig_ab" in e for e in preise["eintraege"])


# --- Formeln & Variablen ----------------------------------------------------- #
async def test_t25_liste_formeln_reverse_dep(lese: LeseModell) -> None:
    # "Welche Formeln hängen am Dieselpreis?"
    liste = await lese.liste_formeln(referenziert_variable="kraftstoffpreis_eur_pro_l")
    namen = {e["name"] for e in liste["eintraege"]}
    assert "mk_fraese" in namen and liste["treffer_gesamt"] >= 5


async def test_t26_zeige_formel_latex_und_reverse(lese: LeseModell) -> None:
    f = await lese.zeige_formel("mk_fraese")
    assert f["latex"] and f["legende"]
    assert any(e["variable"] == "kraftstoffpreis_eur_pro_l" for e in f["eingaben"])
    assert "V_FRAESEN" in f["gebunden_in_vorgaengen"]


async def test_t26_gebunden_auch_ueber_kosten_bindung(lese: LeseModell, engine: AsyncEngine) -> None:
    """A Vorgang whose kosten_bindung names the formula's output variable (a bound machine would
    shadow the formula there) must appear in gebunden_in_vorgaengen — consistent with T30's roles.
    No seeded Vorgang has this shape, so the test activates a synthetic one and archives it again."""
    payload = {
        "name": "Test: Bindung schattet Formel",
        "ausfuehrungsart_code": "AA_KALTFRAESE",
        "betriebsart_code": "regelfraesen",
        "leistung_variable": None,
        "kosten_bindung": {"mk_fraese": "betriebskosten_eur_pro_h"},
        "kostenvariablen": {},
    }
    async with engine.begin() as conn:
        repo = KatalogRepository(conn)
        zeile = await repo.neue_version(
            KatalogEntitaet.VORGAENGE, "V_TEST_BINDUNG", payload, benutzer="test", bundle_uuid=None
        )
        await repo.aktiviere(KatalogEntitaet.VORGAENGE, zeile.zeile_uuid)
    try:
        async with engine.connect() as conn:  # fresh LeseModell: the module-scoped one has cached rows
            frisch = LeseModell(conn)
            f = await frisch.zeige_formel("mk_fraese")
            verwendung = await frisch.verwendung_von_variable("mk_fraese")
        # T26 and T30 share the role definition (_vorgang_rollen) — both must list the Vorgang.
        assert "V_TEST_BINDUNG" in f["gebunden_in_vorgaengen"]
        assert any(
            v["code"] == "V_TEST_BINDUNG" and "kosten_bindung" in v["rollen"]
            for v in verwendung["vorgaenge"]
        )
    finally:
        async with engine.begin() as conn:
            await KatalogRepository(conn).archiviere(KatalogEntitaet.VORGAENGE, zeile.zeile_uuid)


async def test_t27_liste_variablen_gruppe(lese: LeseModell) -> None:
    liste = await lese.liste_variablen(gruppe="stammdaten")
    assert liste["eintraege"]
    assert all(e["gruppe"] == "stammdaten" for e in liste["eintraege"])


async def test_t28_zeige_variable_konstante(lese: LeseModell) -> None:
    v = await lese.zeige_variable("kraftstoffpreis_eur_pro_l")
    assert v["gruppe"] == "stammdaten"
    assert v["konstante_wert"] == "1.75"
    assert v["aufloesung"]


async def test_t29_erklaere_variable_baum(lese: LeseModell) -> None:
    baum = await lese.erklaere_variable("mk_fraese")
    assert baum["methode"] == "formel" and baum["formel"] == "mk_fraese"
    kinder = {k["variable"] for k in baum["eingaben"]}
    assert "kraftstoffpreis_eur_pro_l" in kinder
    diesel = next(k for k in baum["eingaben"] if k["variable"] == "kraftstoffpreis_eur_pro_l")
    assert diesel["methode"] == "konstante"


async def test_t30_verwendung_von_variable(lese: LeseModell) -> None:
    nutzung = await lese.verwendung_von_variable("kraftstoffpreis_eur_pro_l")
    assert "mk_fraese" in nutzung["formeln"] and len(nutzung["formeln"]) >= 5


# --- Globale Variablen ------------------------------------------------------- #
async def test_t31_liste_globale_variablen(lese: LeseModell) -> None:
    liste = await lese.liste_globale_variablen()
    assert liste["eintraege"]
    assert any(e.get("ist_standort") for e in liste["eintraege"])


# --- Lifecycle & Audit ------------------------------------------------------- #
async def test_t32_zeige_historie(lese: LeseModell) -> None:
    hist = await lese.zeige_historie("leistungen", "L_FSS")
    assert len(hist["versionen"]) == 1
    assert hist["versionen"][0]["status"] == "aktiv" and hist["versionen"][0]["version"] == 1


async def test_t33_liste_entwuerfe_leer(lese: LeseModell) -> None:
    entwuerfe = await lese.liste_entwuerfe()
    assert entwuerfe["treffer_gesamt"] == 0


# --- Truncation guard (§10.3) ------------------------------------------------ #
async def test_truncation_nie_still(lese: LeseModell) -> None:
    liste = await lese.liste_formeln(limit=1)
    assert liste["treffer_gesamt"] > 1
    assert len(liste["eintraege"]) == 1
