"""Hand-computed tests for the base-formula engine (REZEPT_REDESIGN_PLAN Phase 1).

Covers the unit converter (exact Decimal scalings, dimension guard), the instanz
binding seams (conversion at the seam, einheiten pins, literals, defaults, the
booked-variable and machine-override short-circuits, cycle detection) and the
curve/selection formulas with hand-computed anchor values.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from shared.services.kalkulation_v2.einheiten import faktor, konvertiere
from shared.services.kalkulation_v2.formel import FORMELN
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M,
    FormelInstanz,
    Kalkulationskontext,
    Kalkulator,
    Kostenart,
    VariablenWert,
    Vorgang,
    VorgangRechnung,
)
from shared.services.kalkulation_v2.store import KATALOG

KALK = Kalkulator(KATALOG, FORMELN)

APPENDIX_A = {
    "F_MENGE_VOLUMEN", "F_VOLUMEN_FLAECHE", "F_FLAECHE_VOLUMEN", "F_VOLUMEN_QUADER",
    "F_MENGE_ANSATZ", "F_ARBEITSMENGE", "F_LAGEN",
    "F_STUNDEN", "F_LOHN", "F_MASCHINE", "F_KOSTEN_SATZ", "F_TRANSPORT",
    "F_LEISTUNG_TIEFE", "F_LEISTUNG_ERSCHWERT", "F_UEBERGAENGE", "F_STAFFEL",
}


def _ctx(**werte: str) -> Kalkulationskontext:
    ctx = Kalkulationskontext(stichtag=date(2026, 6, 22))
    for name, wert in werte.items():
        ctx.werte[name] = VariablenWert(name=name, wert=Decimal(wert), quelle=M.HITL)
    return ctx


def _vorgang(instanzen: dict, kosten: dict, **felder) -> Vorgang:
    return Vorgang(code="V_TEST", name="Test",
                   rechnung=VorgangRechnung(instanzen=instanzen, kosten=kosten), **felder)


def test_basisformel_katalog_ist_appendix_a() -> None:
    assert set(FORMELN) == APPENDIX_A
    for f in FORMELN.values():
        assert f.validieren() == []
        assert (f.beschreibung or "").strip()
        for p in f.parameter:
            assert (p.beschreibung or "").strip(), f"{f.name}.{p.name} ohne Prosa"


def test_alle_variablen_haben_beschreibung() -> None:
    """Phase-3 gate: every surviving stammdaten/kontext variable carries retrieval-grade prose
    (§2.6). Guards the corpus against rotting back to the pre-cleanup state (avg 4 chars)."""
    from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN
    from shared.services.kalkulation_v2.stammdaten import STAMMDATEN_VARIABLEN

    for quelle, label in ((STAMMDATEN_VARIABLEN, "stammdaten"), (KONTEXT_VARIABLEN, "kontext")):
        ohne = [n for n, v in quelle.items() if len((v.beschreibung or "").strip()) < 20]
        assert not ohne, f"{label}: Variablen ohne belastbare beschreibung: {ohne}"


def test_kontext_eingaben_haben_kaskaden_prompt() -> None:
    """Every extracted kontext input (LANGTEXT/RAG cascade) carries a co-authored prompt — the
    executable 'how to find it' beside the human-readable prose. Geometry placeholders (HITL,
    booked from the LV Menge) legitimately carry none."""
    from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN

    for name, v in KONTEXT_VARIABLEN.items():
        methoden = {s.methode for s in v.aufloesung}
        if M.LANGTEXT in methoden or M.RAG in methoden:
            assert any((s.prompt or "").strip() for s in v.aufloesung), f"{name}: Kaskade ohne Prompt"


def test_faktor_exakte_skalierungen() -> None:
    assert faktor("cm", "m") == Decimal("0.01")
    assert faktor("mm", "m") == Decimal("0.001")
    assert faktor("kg", "t") == Decimal("0.001")
    assert faktor("kg/m²", "t/m2") == Decimal("0.001")
    assert faktor("g/(m·cm)", "t/(m·cm)") == Decimal("0.000001")
    assert konvertiere(Decimal("250"), "cm", "m") == Decimal("2.50")


def test_faktor_keine_konvertierung() -> None:
    assert faktor("t", "t") is None                  # identical
    assert faktor("m²/h", None) is None              # no target
    assert faktor("Pers", "-") is None               # unknown unit passes through
    assert faktor("€/(t·km)", "€/(t·km)") is None


def test_faktor_dimensionswechsel_ist_fehler() -> None:
    with pytest.raises(ValueError, match="nicht skalierbar"):
        faktor("m³", "t")


def test_stunden_lohn_maschine_hand_gerechnet() -> None:
    v = _vorgang(
        {
            "leistung": FormelInstanz(formel="F_LEISTUNG_ERSCHWERT",
                                      bindung={"basisleistung": "250"}),
            "arbeitszeit": FormelInstanz(formel="F_STUNDEN",
                                         bindung={"menge": "kontext.flaeche_m2",
                                                  "leistung": "formel.leistung"}),
        },
        {
            Kostenart.MASCHINE: [FormelInstanz(formel="F_MASCHINE", bindung={
                "stunden": "formel.arbeitszeit", "stundensatz": "210",
                "verbrauch": "60", "kraftstoffpreis": "1.75"})],
            Kostenart.LOHN: [FormelInstanz(formel="F_LOHN", bindung={
                "stunden": "formel.arbeitszeit", "stundenlohn": "42", "kolonne": "2"})],
        },
    )
    ctx = _ctx(flaeche_m2="1000")
    r = v.kalkuliere(KALK, ctx)
    # 1000/250 = 4 h; Maschine 4 × (210 + 60×1.75) = 1260 €; Lohn 4 × 42 × 2 = 336 €
    assert r["ekt_eur"] == Decimal("1596.00")
    # the referenced instanz is recorded Vorgang-scoped with FORMEL provenance
    beleg = ctx.werte["V_TEST::arbeitszeit"]
    assert beleg.wert == Decimal("4")
    assert beleg.quelle is M.FORMEL and beleg.beleg == "F_STUNDEN"


def test_bindung_konvertiert_cm_nach_m_am_saum() -> None:
    v = _vorgang(
        {"volumen": FormelInstanz(formel="F_VOLUMEN_FLAECHE",
                                  bindung={"flaeche": "kontext.flaeche_m2",
                                           "dicke": "kontext.tiefe_cm"})},
        {Kostenart.ENTSORGUNG: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                              bindung={"menge": "formel.volumen", "satz": "10"})]},
    )
    r = v.kalkuliere(KALK, _ctx(flaeche_m2="100", tiefe_cm="4"))
    assert r["ekt_eur"] == Decimal("40.00")   # 100 m² × 0.04 m = 4 m³ × 10 €/m³


def test_einheiten_pin_normalisiert_polymorphen_ansatz() -> None:
    v = _vorgang(
        {"menge": FormelInstanz(formel="F_MENGE_ANSATZ", einheiten={"ansatz": "t/m2"},
                                bindung={"ansatz": "kontext.abstreumenge_kg_pro_m2",
                                         "bezugsmenge": "kontext.flaeche_m2"})},
        {Kostenart.MATERIAL: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                            bindung={"menge": "formel.menge", "satz": "30"})]},
    )
    r = v.kalkuliere(KALK, _ctx(flaeche_m2="7800", abstreumenge_kg_pro_m2="1.0"))
    assert r["ekt_eur"] == Decimal("234.00")  # 7800 kg = 7.8 t × 30 €/t


def test_standardwerte_fuellen_ungebundene_parameter() -> None:
    v = _vorgang(
        {"menge": FormelInstanz(formel="F_MENGE_VOLUMEN",   # verdichtungsfaktor unbound -> 1
                                bindung={"volumen": "kontext.volumen_m3", "dichte": "2.40"})},
        {Kostenart.MATERIAL: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                            bindung={"menge": "formel.menge", "satz": "10"})]},
    )
    r = v.kalkuliere(KALK, _ctx(volumen_m3="100"))
    assert r["ekt_eur"] == Decimal("2400.00")


def test_ungebundener_parameter_ohne_standard_wirft() -> None:
    v = _vorgang({}, {Kostenart.MATERIAL: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                                         bindung={"menge": "1"})]})
    with pytest.raises(ValueError, match="ungebunden"):
        v.kalkuliere(KALK, _ctx())


def test_gebuchte_variable_gewinnt_ueber_instanz() -> None:
    # t-billed: menge_t is booked, so the flaeche/einbaudicke chain (whose inputs are
    # deliberately absent from the ctx) must never be evaluated.
    v = _vorgang(
        {
            "volumen": FormelInstanz(formel="F_VOLUMEN_FLAECHE",
                                     bindung={"flaeche": "kontext.flaeche_m2",
                                              "dicke": "kontext.einbaudicke_cm"}),
            "menge": FormelInstanz(formel="F_MENGE_VOLUMEN", variable="menge_t",
                                   bindung={"volumen": "formel.volumen", "dichte": "2.40"}),
        },
        {Kostenart.MATERIAL: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                            bindung={"menge": "formel.menge", "satz": "72"})]},
    )
    r = v.kalkuliere(KALK, _ctx(menge_t="400"))
    assert r["ekt_eur"] == Decimal("28800.00")


def test_maschinen_override_ersetzt_leistung_instanz() -> None:
    v = _vorgang(
        {
            "leistung": FormelInstanz(formel="F_LEISTUNG_ERSCHWERT",
                                      bindung={"basisleistung": "250"}),
            "arbeitszeit": FormelInstanz(formel="F_STUNDEN",
                                         bindung={"menge": "kontext.flaeche_m2",
                                                  "leistung": "formel.leistung"}),
        },
        {Kostenart.LOHN: [FormelInstanz(formel="F_LOHN", bindung={
            "stunden": "formel.arbeitszeit", "stundenlohn": "42"})]},
        leistung_instanz="leistung",
    )
    ctx = _ctx(flaeche_m2="1000")
    scoped = v.instanz_scope("leistung")
    ctx.werte[scoped] = VariablenWert(name=scoped, wert=Decimal("500"), quelle=M.STAMMDATEN)
    r = v.kalkuliere(KALK, ctx)
    assert r["ekt_eur"] == Decimal("84.00")   # 1000/500 = 2 h × 42 € (statt 4 h)


def test_instanz_zyklus_wird_erkannt() -> None:
    v = _vorgang(
        {
            "a": FormelInstanz(formel="F_LEISTUNG_ERSCHWERT", bindung={"basisleistung": "formel.b"}),
            "b": FormelInstanz(formel="F_LEISTUNG_ERSCHWERT", bindung={"basisleistung": "formel.a"}),
        },
        {Kostenart.LOHN: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                        bindung={"menge": "formel.a", "satz": "1"})]},
    )
    with pytest.raises(ValueError, match="Instanz-Zyklus"):
        v.kalkuliere(KALK, _ctx())


def _kurvenwert(instanz: FormelInstanz, **werte: str) -> Decimal:
    """Evaluate a single curve/selection instanz by billing its value through F_KOSTEN_SATZ."""
    v = _vorgang({"kurve": instanz},
                 {Kostenart.LOHN: [FormelInstanz(formel="F_KOSTEN_SATZ",
                                                 bindung={"menge": "formel.kurve", "satz": "1"})]})
    return v.kalkuliere(KALK, _ctx(**werte))["ekt_eur"]


def test_leistung_tiefe_kurve_hand_gerechnet() -> None:
    fraese = FormelInstanz(formel="F_LEISTUNG_TIEFE", bindung={
        "tiefenkonstante": "10", "untergrenze": "120", "tiefe": "kontext.tiefe_cm",
        "erschwernisfaktor": "kontext.erschwernisfaktor"})
    assert _kurvenwert(fraese, tiefe_cm="4", erschwernisfaktor="1.0") == Decimal("250.00")
    # deep cut: 10/0.125 = 80 -> clamped to the 120 m²/h floor
    assert _kurvenwert(fraese, tiefe_cm="12.5", erschwernisfaktor="1.0") == Decimal("120.00")
    # Erschwernis divides
    assert _kurvenwert(fraese, tiefe_cm="4", erschwernisfaktor="2.0") == Decimal("125.00")

    fein = FormelInstanz(formel="F_LEISTUNG_TIEFE", bindung={
        "tiefenkonstante": "10", "obergrenze": "250", "tiefe": "kontext.tiefe_cm"})
    # shallow precision pass: 10/0.02 = 500 -> capped at 250
    assert _kurvenwert(fein, tiefe_cm="2") == Decimal("250.00")


def test_uebergaenge_kurve_hand_gerechnet() -> None:
    kurve = FormelInstanz(formel="F_UEBERGAENGE", bindung={
        "x": "kontext.ev2_ziel", "x0": "45", "y0": "3", "x1": "100", "y1": "6"})
    assert _kurvenwert(kurve, ev2_ziel="45") == Decimal("3.00")
    # ceil(3 + 25 × 3/55) = ceil(4.36) = 5
    assert _kurvenwert(kurve, ev2_ziel="70") == Decimal("5.00")
    # above the upper anchor: clamped to x1
    assert _kurvenwert(kurve, ev2_ziel="200") == Decimal("6.00")


def test_staffel_hand_gerechnet() -> None:
    staffel = FormelInstanz(formel="F_STAFFEL", bindung={
        "wert": "kontext.fraesgut_klasse", "stufe1": "1", "satz1": "0",
        "stufe2": "2", "satz2": "25", "satz3": "110"})
    assert _kurvenwert(staffel, fraesgut_klasse="1") == Decimal("0.00")
    assert _kurvenwert(staffel, fraesgut_klasse="2") == Decimal("25.00")
    assert _kurvenwert(staffel, fraesgut_klasse="3") == Decimal("110.00")


def test_lagen_hand_gerechnet() -> None:
    lagen = FormelInstanz(formel="F_LAGEN", bindung={
        "dicke": "kontext.schichtdicke_m", "max_lagendicke": "0.30"})
    assert _kurvenwert(lagen, schichtdicke_m="0.40") == Decimal("2.00")
    assert _kurvenwert(lagen, schichtdicke_m="0.30") == Decimal("1.00")
