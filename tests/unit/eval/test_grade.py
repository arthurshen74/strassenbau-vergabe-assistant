"""The pure scoring core of the EKT extraction grader.

Covers value matching (tolerance, both-missing, non-numeric), the per-variable rules that keep the
metric valid (an overridden gold is not scored on provenance), and the aggregate over a position set
(EINGABE-only headline, provenance only over assessable leaves)."""

from __future__ import annotations

from scripts.eval_calculator.grade import (
    grade_position,
    grade_variable,
    summarize,
    values_match,
)


def test_values_match_tolerance_and_edges() -> None:
    assert values_match("4", "4") is True
    assert values_match("4.00", "4") is True            # decimal-equal
    assert values_match(None, None) is True             # both absent agree
    assert values_match("4", None) is False             # expected but missing
    assert values_match("4", "x") is False              # non-numeric system value
    assert values_match("4.00", "4.04", abs_tol="0") is False
    assert values_match("4.00", "4.04", abs_tol="0.05") is True


def test_accepted_value_scores_provenance() -> None:
    gold = {"wert": "4", "art": "eingabe", "quelle": "langtext", "overridden": False}
    r = grade_variable("d", gold, {"wert": "4", "quelle": "langtext"})
    assert r.found_expected and r.found_actual and r.value_correct
    assert r.provenance_correct is True


def test_overridden_gold_not_scored_on_provenance() -> None:
    # The Kalkulator overrode this value, so its quelle is hitl, not a real source.
    gold = {"wert": "3.5", "art": "eingabe", "quelle": "hitl", "overridden": True}
    r = grade_variable("b", gold, {"wert": "3.5", "quelle": "langtext"})
    assert r.value_correct is True
    assert r.provenance_correct is None


def test_missed_value() -> None:
    gold = {"wert": "4", "art": "eingabe", "quelle": "langtext", "overridden": False}
    r = grade_variable("d", gold, None)             # the re-run surfaced nothing
    assert r.found_actual is False
    assert r.value_correct is False
    assert r.provenance_correct is False            # expected, not overridden -> assessable and wrong


# a: accepted + correct; b: overridden, re-run disagrees; rate: a SATZ leaf (excluded from headline).
_GOLD_VARS = {
    "a": {"wert": "4", "art": "eingabe", "quelle": "langtext", "overridden": False},
    "b": {"wert": "2", "art": "eingabe", "quelle": "hitl", "overridden": True},
    "rate": {"wert": "50", "art": "satz", "quelle": "konstante", "overridden": False},
}
_PROPOSALS = {
    "a": {"wert": "4", "quelle": "langtext"},
    "b": {"wert": "9", "quelle": "rag"},
    "rate": {"wert": "50", "quelle": "konstante"},
}


def test_summarize_filters_eingabe_and_provenance() -> None:
    hit = grade_position(
        position_id="01",
        gold_leistung_key="L",
        gold_variables=_GOLD_VARS,
        system_leistung_key="L",
        system_proposals=_PROPOSALS,
    )
    miss = grade_position(
        position_id="02",
        gold_leistung_key="L",
        gold_variables={},
        system_leistung_key="X",          # wrong classification
        system_proposals={},
    )
    m = summarize([hit, miss])

    assert m.positions == 2
    assert m.classification_accuracy == 0.5
    assert m.bauverfahren_accuracy is None           # no gold carries a Bauverfahren
    assert m.eingabe_variables == 2                  # a, b (rate is SATZ)
    assert m.expected_values == 2
    assert m.value_accuracy == 0.5                   # a correct, b wrong (9 != 2)
    assert m.found_recall == 1.0                     # both produced a value
    assert m.provenance_accuracy == 1.0              # only a is assessable, and it matches


def test_bauverfahren_graded_only_when_gold_has_one() -> None:
    def pos(pid: str, gold_bv: str | None, system_bv: str | None):
        return grade_position(
            position_id=pid,
            gold_leistung_key="L",
            gold_variables={},
            system_leistung_key="L",
            system_proposals={},
            gold_bauverfahren_key=gold_bv,
            system_bauverfahren_key=system_bv,
        )

    hit = pos("01", "BV_FRAESEN", "BV_FRAESEN")
    miss = pos("02", "BV_FRAESEN", "BV_AUFBRECHEN")
    no_gold = pos("03", None, "BV_FRAESEN")          # gold has no BV -> not assessable

    assert hit.bauverfahren_correct is True
    assert miss.bauverfahren_correct is False
    assert no_gold.bauverfahren_correct is None

    m = summarize([hit, miss, no_gold])
    assert m.bauverfahren_accuracy == 0.5            # over the two assessable positions
