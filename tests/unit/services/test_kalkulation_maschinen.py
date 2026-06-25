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
from shared.services.kalkulation_v2.maschinen import MASCHINEN, maschinen_fuer
from shared.services.kalkulation_v2.maschinen import validate as maschinen_validate
from shared.services.kalkulation_v2.positionen import POSITIONEN
from shared.services.kalkulation_v2.store import kalkuliere

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
