"""Engine tests for kalkulation_v2.

A determinism/regression guard that `kalkuliere` still reproduces the authored
L 101 mill-and-fill fixture after the packaging refactor, plus coverage of the
`benoetigte_variablen` worklist walk that the variable-review gate depends on.
"""

from __future__ import annotations

from decimal import Decimal

from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.leistung_bauverfahren import waehle_bauverfahren
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.model import Kalkulator
from shared.services.kalkulation_v2.positionen import POSITIONEN, P
from shared.services.kalkulation_v2.store import FORMELN, KATALOG, GEOM, kalkuliere
from shared.services.kalkulation_v2.worklist import BlattArt, benoetigte_variablen

# Golden values for the authored L 101 fixture (Bauabschnitt 01). Update only when
# the catalog/rates change on purpose.
L101_EKT_GESAMT = Decimal("557933.35")
L101_POSITIONEN = 41


def test_kalkuliere_reproduces_l101_fixture() -> None:
    gesamt = sum((kalkuliere(p)["ekt_eur"] for p in POSITIONEN), Decimal("0"))
    assert len(POSITIONEN) == L101_POSITIONEN
    assert gesamt.quantize(Decimal("0.01")) == L101_EKT_GESAMT


def test_kalkuliere_fraesen_slice_is_deterministic() -> None:
    pos = next(p for p in POSITIONEN if p.oz == "01.02.0006")   # the 7800 m² fräsen slice
    r1 = kalkuliere(pos)
    r2 = kalkuliere(pos)
    assert r1["bauverfahren"] == "BV_FRAESEN"
    assert r1["ekt_eur"] == r2["ekt_eur"] == Decimal("13347.36")
    assert r1["ep_eur"] == Decimal("1.71")


def _fraesen_worklist() -> list:
    kalk = Kalkulator(KATALOG, FORMELN)
    bv = BAUVERFAHREN[waehle_bauverfahren("L_FRAESEN")]
    geom = GEOM[LEISTUNGEN["L_FRAESEN"].einheit]
    return benoetigte_variablen(bv, kalk, gebucht=frozenset({geom}))


def test_benoetigte_variablen_fraesen_leaf_set() -> None:
    leaves = _fraesen_worklist()
    namen = {b.name for b in leaves}
    assert namen == {
        "erschwernisfaktor",
        "tiefe_cm",
        "anzahl_arbeiter",
        "fraesgut_klasse",
        "entfernung_deponie_km",
        "kaltfraese_l_pro_h",
        "kaltfraese_stundensatz_eur",
        "kraftstoffpreis_eur_pro_l",
        "stundenlohn_eur",
        "ent_fraesgut_belastet",
        "ent_fraesgut_pechhaltig",
        "ent_fraesgut_verwertbar",
        "dichte_asphalt_t_pro_m3",
        "transport_eur_pro_t_km",
    }


def test_benoetigte_variablen_classifies_and_flags() -> None:
    by_name = {b.name: b for b in _fraesen_worklist()}

    # fraesgut_klasse: extracted input, no KONSTANTE fallback -> high-stakes.
    assert by_name["fraesgut_klasse"].art is BlattArt.EINGABE
    assert by_name["fraesgut_klasse"].hochrisiko is True

    # A rate from the rate book: SATZ, never high-stakes.
    assert by_name["stundenlohn_eur"].art is BlattArt.SATZ
    assert by_name["stundenlohn_eur"].hochrisiko is False


def test_benoetigte_variablen_excludes_intermediates_and_booked_geometry() -> None:
    namen = {b.name for b in _fraesen_worklist()}
    # FORMEL intermediates are walked through, never returned.
    assert "menge_t" not in namen
    assert "mk_fraese" not in namen
    # Booking the area from the LV Menge prunes its geometry sub-inputs.
    assert "flaeche_m2" not in namen
    assert "volumen_m3" not in namen
    assert "schichtdicke_m" not in namen


def test_gap_closer_leistungen_classify_and_compute() -> None:
    """The LV-coverage additions (Feinfräsen, Handeinbau, Gussasphalt) are valid
    Leistungen with a recipe and produce a positive EKT."""
    cases = [
        P("T1", "L_FEINFRAESEN", "1000", tiefe_cm="1", fraesgut_klasse="1"),
        P("T2", "L_ASPHALT_HAND", "200", einbaudicke_cm="4"),
        P("T3", "L_GUSSASPHALT_DECK", "300", einbaudicke_cm="3"),
    ]
    for pos in cases:
        assert pos.leistung_key in LEISTUNGEN
        assert waehle_bauverfahren(pos.leistung_key) in BAUVERFAHREN
        assert kalkuliere(pos)["ekt_eur"] > 0


def test_feinfraesen_is_slower_than_regelfraesen() -> None:
    # Same shallow depth: the precision fine-mill is much slower -> a higher unit price.
    fein = kalkuliere(P("Tf", "L_FEINFRAESEN", "1000", tiefe_cm="2", fraesgut_klasse="1"))["ep_eur"]
    regel = kalkuliere(
        P("Tr", "L_FRAESEN", "1000", tiefe_cm="2", erschwernisfaktor="1.0", fraesgut_klasse="1")
    )["ep_eur"]
    assert fein > regel


def test_secondary_gap_leistungen_classify_and_compute() -> None:
    """STS (reuses FSS recipes, multi-candidate), DSK, Randabdichtung."""
    sts = P("S1", "L_STS", "100", baustoff="STS_0_32", materialpreis_eur_pro_t="18.50",
            entfernung_lieferant_km="14", schichtdicke_m="0.20", ev2_ziel="100", anzahl_arbeiter="3")
    assert waehle_bauverfahren("L_STS") == "BV_FSS_GRADER"          # default
    assert "BV_FSS_FERTIGER" in BAUVERFAHREN and waehle_bauverfahren("L_STS", "BV_FSS_FERTIGER")
    for pos in (sts, P("D1", "L_DSK", "2000"), P("R1", "L_RANDABDICHTUNG", "500")):
        assert pos.leistung_key in LEISTUNGEN
        assert kalkuliere(pos)["ekt_eur"] > 0
