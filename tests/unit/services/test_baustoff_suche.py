"""Tests for the BM25 Baustoff matcher + the recipe material-need predicate.

The matcher grounds an LV text (normed TL SoB-StB / TL Asphalt-StB designations) to a real
catalog code — it can only ever return a cataloged code. `braucht_baustoff` gates which
recipes trigger material selection at all.
"""

from __future__ import annotations

from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.baustoff_suche import suche_baustoff
from shared.services.kalkulation_v2.model import Kalkulator
from shared.services.kalkulation_v2.store import FORMELN, KATALOG
from shared.services.kalkulation_v2.worklist import braucht_baustoff

KALK = Kalkulator(KATALOG, FORMELN)


def test_normed_designations_match_correct_code() -> None:
    cases = {
        "Schottertragschicht 0/32 herstellen Bk100": "STS_0_32",
        "Frostschutzschicht aus Mineralgemisch 0/45 einbauen": "FSS_0_45",
        "Asphaltdeckschicht AC 11 D S herstellen": "ASPHALT_AC11DS",
        "Splittmastixasphalt SMA 8 S Deckschicht": "SMA_8_S",
        "Asphalttragschicht AC 32 T S einbauen": "ASPHALT_AC32TS",
        "RC-Schotter 0/45 als Tragschicht": "RC_SCHOTTER_0_45",
    }
    for text, code in cases.items():
        assert suche_baustoff(text).top.code == code, text


def test_koernung_discriminates_grades() -> None:
    # Same type word, different Körnung -> different grade.
    assert suche_baustoff("Frostschutzschicht 0/32").top.code == "FSS_0_32"
    assert suche_baustoff("Frostschutzschicht 0/45").top.code == "FSS_0_45"


def test_grounded_to_catalog_and_confidence_range() -> None:
    from shared.services.kalkulation_v2.materialien import BAUSTOFFE

    m = suche_baustoff("Schottertragschicht 0/32")
    assert m.top.code in BAUSTOFFE                      # never a hallucinated code
    assert 0.5 <= m.konfidenz <= 1.0                    # separation confidence band
    # Distinctive type code => clear winner => high confidence.
    assert suche_baustoff("Splittmastixasphalt SMA 8 S").konfidenz > m.konfidenz


def test_no_material_text_yields_no_hit() -> None:
    m = suche_baustoff("Markierung entfernen und Fläche reinigen")
    # Cleaning/milling text has no material token -> no hit, zero confidence (=> HITL).
    assert m.top is None
    assert m.konfidenz == 0.0


def test_braucht_baustoff_only_for_graded_material_recipes() -> None:
    # FSS/STS lay a graded material by tonnage (density from the Baustoff) -> need one.
    assert braucht_baustoff(BAUVERFAHREN["BV_FSS_GRADER"], KALK)
    assert braucht_baustoff(BAUVERFAHREN["BV_FSS_FERTIGER"], KALK)
    # Fräsen uses no material; DSK/Gussasphalt price material directly (no Baustoff density).
    assert not braucht_baustoff(BAUVERFAHREN["BV_FRAESEN"], KALK)
    assert not braucht_baustoff(BAUVERFAHREN["BV_DSK"], KALK)
    assert not braucht_baustoff(BAUVERFAHREN["BV_GUSSASPHALT"], KALK)
