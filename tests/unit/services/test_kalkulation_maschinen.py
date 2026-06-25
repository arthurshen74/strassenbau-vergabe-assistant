"""Tests for the kalkulation_v2 machine catalog (Betriebsarten + Maschinen).

Load-time integrity (FKs), fleet coverage of the mill-and-fill slots, the mixed
Decimal/str/bool property bag, per-Betriebsart profiles (+ a profile-specific cost
override), and a guard that adding the catalog left the calc golden untouched.
"""

from __future__ import annotations

from decimal import Decimal

from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN
from shared.services.kalkulation_v2.betriebsarten import (
    BETRIEBSARTEN,
    BETRIEBSKATEGORIEN,
)
from shared.services.kalkulation_v2.betriebsarten import validate as betriebsarten_validate
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.binden import maschinen_werte, rezept_maschinen_werte
from shared.services.kalkulation_v2.maschinen import MASCHINEN, maschinen_fuer
from shared.services.kalkulation_v2.maschinen import validate as maschinen_validate
from shared.services.kalkulation_v2.model import AufloesungsMethode as M
from shared.services.kalkulation_v2.model import Kalkulationskontext, VariablenWert
from shared.services.kalkulation_v2.positionen import POSITIONEN
from shared.services.kalkulation_v2.store import STICHTAG, kalkuliere, kalkuliere_kontext
from shared.services.kalkulation_v2.vorgaenge import VORGAENGE

# The machine-led mill-and-fill slots the fleet must cover (the hand-device crews
# AA_KOLONNE / AA_GRID_KOLONNE intentionally have no fleet entry -> org-rate/HITL).
COVERED_SLOTS = {
    "AA_KALTFRAESE", "AA_MARKFRAESE", "AA_BAGGER", "AA_SCHNEIDER", "AA_RADLADER",
    "AA_GRADER_SOLO", "AA_WALZE", "AA_BANKETTWALZE", "AA_FERTIGER", "AA_ASPHALT_FERTIGER",
    "AA_BANKETT_FERTIGER", "AA_KEHRMASCHINE", "AA_HD_WASCHSAUG", "AA_SPRITZGERAET",
    "AA_ABSTREUER", "AA_FUGENGERAET", "AA_RADLADER_WALZE", "AA_GRADER", "AA_GUSSASPHALT", "AA_DSK",
}


def test_taxonomy_loads_and_fks_valid() -> None:
    assert betriebsarten_validate() == []
    assert len(BETRIEBSKATEGORIEN) >= 10
    assert len(BETRIEBSARTEN) >= 20
    for b in BETRIEBSARTEN.values():
        assert b.kategorie_code in BETRIEBSKATEGORIEN


def test_fleet_loads_and_fks_valid() -> None:
    assert maschinen_validate() == []
    aa_codes = {a.code for a in AUSFUEHRUNGSARTEN.values()}
    for m in MASCHINEN.values():
        assert m.ausfuehrungsart_code in aa_codes
        for p in m.leistungsprofile:
            assert p.betriebsart_code in BETRIEBSARTEN


def test_fleet_covers_every_mill_and_fill_slot() -> None:
    for slot in COVERED_SLOTS:
        assert maschinen_fuer(slot), f"no machine for slot {slot}"


def test_property_bag_holds_decimal_text_and_bool() -> None:
    w35i = MASCHINEN["WIRTGEN_W35I"]
    assert isinstance(w35i.eigenschaft("betriebskosten_eur_pro_h").wert, Decimal)
    assert w35i.eigenschaft("verfahren").wert == "Fräsen"              # text spec
    w100 = MASCHINEN["WIRTGEN_W100CFI"]
    assert w100.eigenschaft("gnss_steuerung").wert is True            # bool spec


def test_profile_lookup_and_per_profile_cost_override() -> None:
    w100 = MASCHINEN["WIRTGEN_W100CFI"]
    assert w100.leistung_fuer("regelfraesen").leistung == Decimal("520")
    assert w100.leistung_fuer("feinfraesen").leistung == Decimal("240")
    assert w100.leistung_fuer("unbekannt") is None
    # The Bagger's Aufbrechen profile overrides operating cost (breaker wear).
    bagger = MASCHINEN["CAT_323"]
    aufbruch = bagger.leistung_fuer("asphalt_aufbrechen")
    assert aufbruch.eigenschaften["betriebskosten_eur_pro_h"].wert == Decimal("155")


def test_catalog_addition_left_golden_unchanged() -> None:
    gesamt = sum((kalkuliere(p)["ekt_eur"] for p in POSITIONEN), Decimal("0"))
    assert gesamt.quantize(Decimal("0.01")) == Decimal("557933.35")


def test_maschinen_werte_fills_cost_and_productivity_vars() -> None:
    werte = maschinen_werte(VORGAENGE["FRAESEN"], MASCHINEN["WIRTGEN_W100CFI"])
    # cost vars from the property bag + productivity from the regelfraesen profile.
    assert werte["kaltfraese_stundensatz_eur"].wert == Decimal("240")
    assert werte["kaltfraese_l_pro_h"].wert == Decimal("55")
    assert werte["fraese_leistung_m2_pro_h"].wert == Decimal("520")
    assert werte["fraese_leistung_m2_pro_h"].quelle is M.STAMMDATEN
    assert "Wirtgen W 100 CFi" in werte["kaltfraese_stundensatz_eur"].beleg


def _fraesen_ekt(maschine_code: str | None = None) -> Decimal:
    bv = BAUVERFAHREN["BV_FRAESEN"]
    menge = Decimal("7800")
    ctx = Kalkulationskontext(stichtag=STICHTAG, stammdaten={})
    ctx.werte["flaeche_m2"] = VariablenWert(name="flaeche_m2", wert=menge, quelle=M.LANGTEXT)
    for name, value in {"tiefe_cm": "4", "fraesgut_klasse": "1"}.items():
        ctx.werte[name] = VariablenWert(name=name, wert=Decimal(value), quelle=M.HITL)
    if maschine_code:
        ctx.werte.update(rezept_maschinen_werte(bv, {"AA_KALTFRAESE": MASCHINEN[maschine_code]}))
    return kalkuliere_kontext("L_FRAESEN_3_45", "BV_FRAESEN", ctx, menge)["ekt_eur"]


def test_machine_selection_changes_the_ekt() -> None:
    base = _fraesen_ekt()                         # org-default Kaltfräse rate/productivity
    w100 = _fraesen_ekt("WIRTGEN_W100CFI")        # 240 €/h, 520 m²/h
    w150 = _fraesen_ekt("WIRTGEN_W150CFI")        # 310 €/h, 850 m²/h (faster)
    assert w100 != base
    # Both machines are faster than the conservative org productivity -> cheaper,
    # and the faster W150 is cheaper still despite its higher hourly rate.
    assert w150 < w100 < base
