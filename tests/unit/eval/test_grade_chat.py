"""The pure scoring core of the chat-value extraction grader.

Covers the per-assignment status rules (correct / wrong_value / spurious / missed) and the aggregate
(precision/recall/F1 over name+value, plus name_recall and value_accuracy diagnostics)."""

from __future__ import annotations

from scripts.eval_calculator.grade_chat import (
    grade_chat_fixture,
    grade_chat_values,
    summarize_chat,
)


def test_assignment_statuses() -> None:
    status = {r.name: r.status for r in grade_chat_values({"a": "4", "b": "5"}, {"a": "4", "b": "6", "c": "9"})}
    assert status["a"] == "correct"        # name in gold, value matches
    assert status["b"] == "wrong_value"    # name in gold, value differs
    assert status["c"] == "spurious"       # emitted a name not in gold


def test_missed_assignment() -> None:
    status = {r.name: r.status for r in grade_chat_values({"a": "4"}, {})}
    assert status["a"] == "missed"


def test_tolerance_and_decimal_equality() -> None:
    assert grade_chat_values({"a": "4.0"}, {"a": "4"})[0].status == "correct"
    assert grade_chat_values({"a": "4"}, {"a": "4.04"}, abs_tol="0.05")[0].status == "correct"
    assert grade_chat_values({"a": "4"}, {"a": "4.04"})[0].status == "wrong_value"


def test_summary_precision_recall() -> None:
    f1 = grade_chat_fixture(
        "f1", {"tiefe_cm": "4", "fraesgut_klasse": "3"}, {"tiefe_cm": "4", "fraesgut_klasse": "3"}
    )
    f2 = grade_chat_fixture(
        "f2",
        {"einbaudicke_cm": "4", "anzahl_arbeiter": "5"},
        {"einbaudicke_cm": "4", "anzahl_arbeiter": "6", "entfernung_km": "22"},
    )
    m = summarize_chat([f1, f2])

    assert m.fixtures == 2
    assert m.gold_assignments == 4
    assert m.system_assignments == 5
    assert m.correct == 3
    assert m.precision == 0.6                       # 3 / 5 emitted
    assert m.recall == 0.75                         # 3 / 4 gold
    assert abs(m.f1 - (2 * 0.6 * 0.75) / (0.6 + 0.75)) < 1e-9
    assert m.name_recall == 1.0                     # every gold name was emitted
    assert m.value_accuracy == 0.75                 # of emitted gold names, 3/4 right
    assert m.spurious == 1
    assert m.exact_fixtures == 1                     # only f1 is fully correct
