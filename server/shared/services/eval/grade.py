"""Score the calculator's variable extraction against saved ground truth.

Pure functions: given a position's gold record (leistung_key + bauverfahren_key +
gold_variables) and the system's fresh Gate B proposals from a re-run, produce
per-variable and per-position results, then aggregate. The system's Bauverfahren choice
(its Gate 2 default) is graded against gold where gold carries one. Values are compared
as Decimals -- the proposals and the gold are already engine-coerced decimal strings --
so grading is deterministic, no LLM judge. EINGABE leaves are the model-extracted ones
(SATZ and STAMMDATEN come from the catalog) and carry the headline accuracy. A gold
value that the Kalkulator overrode is not scored on provenance (its quelle is hitl, not
a real source)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# BlattArt value of a model-extracted leaf (the LANGTEXT/RAG cascade); the others are
# catalog lookups.
ART_EINGABE = "eingabe"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def values_match(gold: Any, system: Any, *, abs_tol: str = "0") -> bool:
    """Both empty agree; otherwise both must parse as numbers and differ by at most
    abs_tol."""
    g, s = _to_decimal(gold), _to_decimal(system)
    if g is None or s is None:
        return g is None and s is None
    return abs(g - s) <= Decimal(abs_tol)


@dataclass(frozen=True)
class VariableResult:
    name: str
    art: str | None
    gold_wert: str | None
    system_wert: str | None
    gold_quelle: str | None
    system_quelle: str | None
    overridden: bool  # the gold value came from a human override (model missed/erred)
    found_expected: bool  # gold has a value
    found_actual: bool  # the re-run produced a value
    value_correct: bool
    provenance_correct: (
        bool | None
    )  # None when not assessable (overridden gold / no expected value)


def grade_variable(
    name: str,
    gold: dict[str, Any],
    proposal: dict[str, Any] | None,
    *,
    abs_tol: str = "0",
) -> VariableResult:
    gold_wert = gold.get("wert")
    gold_quelle = gold.get("quelle")
    art = gold.get("art")
    overridden = bool(gold.get("overridden"))
    system_wert = proposal.get("wert") if proposal else None
    system_quelle = proposal.get("quelle") if proposal else None
    found_expected = gold_wert is not None
    # Provenance is only meaningful when the model's own proposal was endorsed (not
    # overridden) and a value is expected; an overridden gold carries quelle=hitl, which
    # is not a real source.
    provenance_correct = (
        None if overridden or not found_expected else system_quelle == gold_quelle
    )
    return VariableResult(
        name=name,
        art=art,
        gold_wert=gold_wert,
        system_wert=system_wert,
        gold_quelle=gold_quelle,
        system_quelle=system_quelle,
        overridden=overridden,
        found_expected=found_expected,
        found_actual=system_wert is not None,
        value_correct=values_match(gold_wert, system_wert, abs_tol=abs_tol),
        provenance_correct=provenance_correct,
    )


@dataclass(frozen=True)
class PositionResult:
    id: str
    gold_leistung_key: str
    system_leistung_key: str | None
    classification_correct: bool
    gold_bauverfahren_key: str | None
    system_bauverfahren_key: str | None
    bauverfahren_correct: bool | None  # None when gold carries no Bauverfahren
    variables: list[VariableResult]


def grade_position(
    *,
    position_id: str,
    gold_leistung_key: str,
    gold_variables: dict[str, dict[str, Any]],
    system_leistung_key: str | None,
    system_proposals: dict[str, dict[str, Any]],
    gold_bauverfahren_key: str | None = None,
    system_bauverfahren_key: str | None = None,
    abs_tol: str = "0",
) -> PositionResult:
    variables = [
        grade_variable(name, gold, system_proposals.get(name), abs_tol=abs_tol)
        for name, gold in gold_variables.items()
    ]
    return PositionResult(
        id=position_id,
        gold_leistung_key=gold_leistung_key,
        system_leistung_key=system_leistung_key,
        classification_correct=system_leistung_key == gold_leistung_key,
        gold_bauverfahren_key=gold_bauverfahren_key,
        system_bauverfahren_key=system_bauverfahren_key,
        bauverfahren_correct=(
            None
            if gold_bauverfahren_key is None
            else system_bauverfahren_key == gold_bauverfahren_key
        ),
        variables=variables,
    )


@dataclass(frozen=True)
class Metrics:
    positions: int
    classification_accuracy: float | None
    bauverfahren_accuracy: (
        float | None
    )  # over positions whose gold carries a Bauverfahren
    eingabe_variables: int  # model-extracted leaves seen across all positions
    expected_values: int  # of those, the ones with a value to find
    value_accuracy: (
        float | None
    )  # fraction of expected values the re-run got right (within tol)
    found_recall: float | None  # fraction of expected values the re-run found at all
    provenance_accuracy: (
        float | None
    )  # fraction of assessable leaves with the right source


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def summarize(results: list[PositionResult]) -> Metrics:
    eingabe = [v for r in results for v in r.variables if v.art == ART_EINGABE]
    expected = [v for v in eingabe if v.found_expected]
    assessable = [v for v in eingabe if v.provenance_correct is not None]
    bv_assessable = [r for r in results if r.bauverfahren_correct is not None]
    return Metrics(
        positions=len(results),
        classification_accuracy=_ratio(
            sum(1 for r in results if r.classification_correct), len(results)
        ),
        bauverfahren_accuracy=_ratio(
            sum(1 for r in bv_assessable if r.bauverfahren_correct), len(bv_assessable)
        ),
        eingabe_variables=len(eingabe),
        expected_values=len(expected),
        value_accuracy=_ratio(
            sum(1 for v in expected if v.value_correct), len(expected)
        ),
        found_recall=_ratio(sum(1 for v in expected if v.found_actual), len(expected)),
        provenance_accuracy=_ratio(
            sum(1 for v in assessable if v.provenance_correct), len(assessable)
        ),
    )


def position_to_dict(result: PositionResult) -> dict[str, Any]:
    return asdict(result)


def metrics_to_dict(metrics: Metrics) -> dict[str, Any]:
    return asdict(metrics)
