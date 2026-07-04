"""Score the EKT_CHAT_VALUES transcript-harvest against authored fixtures.

The chat extractor reads the pre-launch transcript and emits variable -> value assignments. A fixture
pairs a transcript with the assignments the Kalkulator actually stated (gold). Grading is set-shaped:
each emitted assignment is a true positive only when its name is in gold AND the value matches; a name
not in gold is spurious, a gold name not emitted is missed. Values compare as Decimals (the runner
coerces verbatim reads the way the graph node does), so this is deterministic -- no LLM judge."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from shared.services.eval.grade import values_match

STATUS_CORRECT = "correct"
STATUS_WRONG_VALUE = "wrong_value"
STATUS_SPURIOUS = "spurious"        # emitted a name that is not in gold
STATUS_MISSED = "missed"            # gold name the extractor did not emit


@dataclass(frozen=True)
class ChatAssignmentResult:
    name: str
    gold_wert: str | None
    system_wert: str | None
    value_correct: bool
    status: str


@dataclass(frozen=True)
class ChatFixtureResult:
    id: str
    assignments: list[ChatAssignmentResult]


def grade_chat_values(
    gold: dict[str, str], system: dict[str, str | None], *, abs_tol: str = "0"
) -> list[ChatAssignmentResult]:
    out: list[ChatAssignmentResult] = []
    for name in sorted(set(gold) | set(system)):
        in_gold, in_system = name in gold, name in system
        gold_wert = gold.get(name)
        system_wert = system.get(name)
        value_correct = in_gold and in_system and values_match(gold_wert, system_wert, abs_tol=abs_tol)
        if not in_gold:
            status = STATUS_SPURIOUS
        elif not in_system:
            status = STATUS_MISSED
        elif value_correct:
            status = STATUS_CORRECT
        else:
            status = STATUS_WRONG_VALUE
        out.append(ChatAssignmentResult(name, gold_wert, system_wert, value_correct, status))
    return out


def grade_chat_fixture(
    fixture_id: str, gold: dict[str, str], system: dict[str, str | None], *, abs_tol: str = "0"
) -> ChatFixtureResult:
    return ChatFixtureResult(fixture_id, grade_chat_values(gold, system, abs_tol=abs_tol))


@dataclass(frozen=True)
class ChatMetrics:
    fixtures: int
    gold_assignments: int
    system_assignments: int
    correct: int
    precision: float | None        # correct / emitted
    recall: float | None           # correct / gold
    f1: float | None
    name_recall: float | None      # gold names emitted (regardless of value) / gold
    value_accuracy: float | None   # of emitted gold names, fraction with the right value
    spurious: int                  # emitted names not in gold
    exact_fixtures: int            # fixtures where every gold assignment is correct and none spurious


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def _f1(precision: float | None, recall: float | None) -> float | None:
    if not precision or not recall:
        return None
    return 2 * precision * recall / (precision + recall)


def summarize_chat(results: list[ChatFixtureResult]) -> ChatMetrics:
    assignments = [a for r in results for a in r.assignments]
    # An assignment belongs to gold unless it is purely spurious; it is emitted unless it was missed.
    gold_n = sum(1 for a in assignments if a.status != STATUS_SPURIOUS)
    system_n = sum(1 for a in assignments if a.status != STATUS_MISSED)
    correct = sum(1 for a in assignments if a.status == STATUS_CORRECT)
    name_hits = sum(1 for a in assignments if a.status in (STATUS_CORRECT, STATUS_WRONG_VALUE))
    precision = _ratio(correct, system_n)
    recall = _ratio(correct, gold_n)
    return ChatMetrics(
        fixtures=len(results),
        gold_assignments=gold_n,
        system_assignments=system_n,
        correct=correct,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        name_recall=_ratio(name_hits, gold_n),
        value_accuracy=_ratio(correct, name_hits),
        spurious=sum(1 for a in assignments if a.status == STATUS_SPURIOUS),
        exact_fixtures=sum(
            1 for r in results
            if r.assignments and all(a.status == STATUS_CORRECT for a in r.assignments)
        ),
    )


def chat_fixture_to_dict(result: ChatFixtureResult) -> dict[str, object]:
    return asdict(result)


def chat_metrics_to_dict(metrics: ChatMetrics) -> dict[str, object]:
    return asdict(metrics)
