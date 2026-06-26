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
        "Asphaltdeckschicht AC 8 D S einbauen": "ASPHALT_AC8DS",
        "Splittmastixasphalt SMA 8 S Deckschicht": "SMA_8_S",
        "Gussasphaltdeckschicht MA 8 S herstellen": "GUSSASPHALT_MA8S",
        "Asphalttragschicht AC 32 T S einbauen": "ASPHALT_AC32TS",
        "Asphalttragschicht AC 22 T S herstellen": "ASPHALT_AC22TS",
        "RC-Schotter 0/45 als Tragschicht": "RC_SCHOTTER_0_45",
        # specialty materials priced per Einheit (m²/m/t)
        "DSK aus DSK 5 herstellen Einbaubreite": "DSK_5",
        "Asphalteinlage Gitter mit Vliesstoff verlegen": "ASPHALTEINLAGE_GITTER",
        "Fugenfüllung Querfuge Fugenmasse N2 herstellen": "FUGENMASSE_N2",
        "Randabdichtung Abd 25/55 herstellen": "RANDABDICHTUNG_ABD2555",
        "Abstumpfung LFK 1/3 maschinell": "ABSTREUSPLITT_1_3",
        "Bitumenemulsion C60 aufsprühen Verbund": "EMULSION_VERBUND",
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


def test_braucht_baustoff_for_material_recipes() -> None:
    # Every material-consuming recipe selects a Baustoff: unbound (density bridge),
    # asphalt/gussasphalt (mix price), and DSK/anspritzen/naht/fugen/abstumpfen/grid
    # (product price per Einheit). A per-position kontext value still overrides.
    for bv in ("BV_FSS_GRADER", "BV_ASPHALT_EINBAU", "BV_GUSSASPHALT", "BV_DSK",
               "BV_ANSPRITZEN", "BV_NAHT", "BV_FUGENFUELLUNG", "BV_ABSTUMPFEN", "BV_GRID",
               "BV_RANDABDICHTUNG"):
        assert braucht_baustoff(BAUVERFAHREN[bv], KALK), bv
    # Pure operations consume no material -> no Baustoff.
    for bv in ("BV_FRAESEN", "BV_SCHNEIDEN", "BV_MARKIERUNG", "BV_REINIGEN_KEHREN", "BV_VERDICHTEN"):
        assert not braucht_baustoff(BAUVERFAHREN[bv], KALK), bv
