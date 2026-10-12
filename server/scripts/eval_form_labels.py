"""Score the form labels of `eval/forms/` against a toggle detector and the chat API.

`--boxes` is offline: for every label file it runs the detector named by `--detector
module:function` (a callable `pdf_bytes -> list[Toggle]`), the pipeline's
marginal-token merge and toggle attachment (`attach_toggles(lines, toggles,
document_uuid)`), and matches every detected option line to a label by page,
bbox overlap and text containment. `--detector none` prints label statistics only.

`--facts` asks every gold fact through `POST /conversations/{uuid}/turn` on a running
stack, `--repeat` times in fresh conversations, and grades the stored assistant message:
`yes_no` by the first ja/nein token, `value` and `list` by containment of every gold
string. This is a report, not a test: the exit code is always 0.

    PYTHONPATH=server uv run python -m scripts.eval_form_labels --boxes --detector none
    PYTHONPATH=server uv run python -m scripts.eval_form_labels --facts \
        --modality plus --bm25
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict

from scripts.form_labeler.store import (
    FactKind,
    FormLabels,
    LineLabel,
    LineState,
    list_fact_files,
    list_label_files,
    load_facts,
    load_labels,
)
from shared.models.enums import MessageKind, PromptType, RetrievalModality
from shared.models.source_line import NewSourceLine
from shared.services.ingestion.extraction import extract_source_lines

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LABELS_ROOT = REPO_ROOT / "eval" / "forms"
DEFAULT_CORPUS = REPO_ROOT / "server" / "training"
DEFAULT_DETECTOR = "shared.services.ingestion.forms.flattened:find_boxes"
DETECTOR_NONE = "none"
TOGGLES_MODULE = "shared.services.ingestion.forms.toggles"
FORM_MODEL_MODULE = "shared.services.ingestion.forms.model"
ATTR_MERGE = "merge_marginal_tokens"
ATTR_ATTACH = "attach_toggles"
ATTR_CHECKED_PREFIX = "OPTION_CHECKED_PREFIX"
ATTR_UNCHECKED_PREFIX = "OPTION_UNCHECKED_PREFIX"

DEFAULT_API = "http://localhost:8000"
DEFAULT_REPEAT = 3
CONVERSATION_TITLE = "form-eval-{tender}-{n}"
PATH_PROJECTS = "/projects"
PATH_CONVERSATIONS = "/conversations"
PATH_TURN = "/conversations/{uuid}/turn"
PATH_MESSAGES = "/conversations/{uuid}/messages"
PATH_CONVERSATION = "/conversations/{uuid}"
SSE_EVENT_PREFIX = "event: "
SSE_EVENT_DONE = "done"
TURN_TIMEOUT_S = 600.0
FIELD_PROJECT_UUID = "project_uuid"
FIELD_PROJECT_NAME = "project_name"
FIELD_VERGABE_ID = "vergabe_id"
FIELD_CONVERSATION_UUID = "conversation_uuid"
FIELD_KIND = "kind"
FIELD_CONTENT = "content"
FIELD_PROMPT_TYPE = "prompt_type"
FIELD_TITLE = "title"
FIELD_RETRIEVAL = "retrieval"
FIELD_MODALITY = "modality"
FIELD_MULTI_QUERY = "multi_query"
FIELD_USE_BM25 = "use_bm25"
FIELD_USE_CROSS_ENCODER = "use_cross_encoder"

Y_TOLERANCE = 4.0
YES = "ja"
NO = "nein"
FAMILY_UNKNOWN = "ohne id"
MARKER_PREFIXES = ("[x]", "[ ]")
LEADING_TOKEN = re.compile(r"^(?:[xX×✓✔]|\d+(?:\.\d+)*)\s+")
WORD = re.compile(r"[a-zäöüß]+")
WHITESPACE = re.compile(r"\s+")

Detector = Callable[[bytes], list[Any]]


class DetectedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    bbox: tuple[float, float, float, float]
    text: str
    state: LineState


class BoxScore(BaseModel):
    """Per-family box counts; `misses`, `false_positives` and `wrong_state` carry the
    offending lines for the report."""

    model_config = ConfigDict(extra="forbid")

    labelled: int = 0
    detected: int = 0
    true_positives: int = 0
    wrong_state: list[str] = []
    false_positives: list[str] = []
    misses: list[str] = []

    @property
    def precision(self) -> float:
        return self.true_positives / self.detected if self.detected else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.labelled if self.labelled else 0.0

    def add(self, other: BoxScore) -> BoxScore:
        return BoxScore(
            labelled=self.labelled + other.labelled,
            detected=self.detected + other.detected,
            true_positives=self.true_positives + other.true_positives,
            wrong_state=self.wrong_state + other.wrong_state,
            false_positives=self.false_positives + other.false_positives,
            misses=self.misses + other.misses,
        )


# --- pure helpers -----------------------------------------------------------------


def normalise_text(text: str) -> str:
    """Lowercase, single spaces, without an option marker or a leading marginal
    token."""
    stripped = text.strip()
    for prefix in MARKER_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
    stripped = LEADING_TOKEN.sub("", stripped.strip())
    return WHITESPACE.sub(" ", stripped).strip().lower()


def lines_match(
    label: LineLabel, page: int, bbox: tuple[float, ...], text: str
) -> bool:
    """Same page, vertical overlap (or tops within tolerance) and text containment in
    either direction, so a merged line still matches the original label line."""
    if page != label.page:
        return False
    overlap = min(label.bbox[3], bbox[3]) - max(label.bbox[1], bbox[1])
    if overlap <= 0 and abs(label.bbox[1] - bbox[1]) > Y_TOLERANCE:
        return False
    a, b = normalise_text(label.text), normalise_text(text)
    return bool(a) and bool(b) and (a in b or b in a)


def score_boxes(labels: list[LineLabel], detected: list[DetectedLine]) -> BoxScore:
    score = BoxScore(labelled=len(labels), detected=len(detected))
    unmatched = list(detected)
    for label in labels:
        hit = next(
            (d for d in unmatched if lines_match(label, d.page, d.bbox, d.text)), None
        )
        if hit is None:
            score.misses.append(_describe(label.page, label.text, label.state))
            continue
        unmatched.remove(hit)
        if hit.state is label.state:
            score.true_positives += 1
        else:
            score.wrong_state.append(
                f"{_describe(hit.page, hit.text, hit.state)} "
                f"(Label {label.state.value})"
            )
    score.false_positives = [_describe(d.page, d.text, d.state) for d in unmatched]
    return score


def grade_yes_no(answer: str) -> str | None:
    """`ja` or `nein` from the first such word of the answer, else None."""
    for word in WORD.findall(answer.lower()):
        if word in (YES, NO):
            return word
    return None


def grade_contains(answer: str, gold: Iterable[str]) -> bool:
    haystack = WHITESPACE.sub(" ", answer).lower()
    return all(WHITESPACE.sub(" ", item).lower() in haystack for item in gold)


def gold_items(gold: str | list[str] | None) -> list[str]:
    if gold is None:
        return []
    return gold if isinstance(gold, list) else [gold]


def resolve_project(projects: list[dict[str, Any]], tender: str) -> str | None:
    """The project whose vergabe_id or name is contained in, or contains, the tender
    folder name (case-insensitive); None when nothing matches."""
    needle = tender.lower()
    for project in projects:
        for field in (FIELD_VERGABE_ID, FIELD_PROJECT_NAME):
            value = (project.get(field) or "").lower()
            if value and (value in needle or needle in value):
                return str(project[FIELD_PROJECT_UUID])
    return None


def family_of(form_id: str | None) -> str:
    return form_id.rsplit(" ", 1)[0] if form_id else FAMILY_UNKNOWN


def _describe(page: int, text: str, state: LineState) -> str:
    return f"S.{page} {state.value:9} {text}"


# --- boxes ------------------------------------------------------------------------


def run_boxes(labels_root: Path, corpus: Path, detector_spec: str) -> None:
    files = list_label_files(labels_root)
    if not files:
        print(f"keine Label-Dateien unter {labels_root}")
        return
    detector = None if detector_spec == DETECTOR_NONE else _load_callable(detector_spec)
    attach = _load_attachment() if detector else None
    by_family: dict[str, BoxScore] = {}
    details: list[tuple[str, BoxScore]] = []
    for path in files:
        labels = load_labels(path)
        family = family_of(labels.form_id)
        if detector is None or attach is None:
            score = BoxScore(labelled=len(labels.lines))
        else:
            pdf_bytes = (corpus / labels.tender / labels.pdf).read_bytes()
            detected = attach(pdf_bytes, detector(pdf_bytes))
            score = score_boxes(labels.lines, _on_labelled_pages(labels, detected))
        by_family[family] = by_family.get(family, BoxScore()).add(score)
        details.append((f"{labels.tender} / {labels.pdf}", score))
    _print_box_table(by_family, with_detector=detector is not None)
    if detector is not None:
        _print_box_details(details)
    else:
        _print_label_stats(files)


def _on_labelled_pages(
    labels: FormLabels, detected: list[DetectedLine]
) -> list[DetectedLine]:
    pages = set(labels.labelled_pages)
    return [d for d in detected if d.page in pages]


def _load_callable(spec: str) -> Callable[..., Any]:
    module_name, _, attr = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        sys.exit(
            f"Detector {spec!r} nicht importierbar ({exc}); --detector none nutzen"
        )
    return getattr(module, attr)


def _load_attachment() -> Callable[[bytes, list[Any]], list[DetectedLine]]:
    """The pipeline's merge + attach steps, imported lazily because they arrive with
    task 08."""
    try:
        toggles = importlib.import_module(TOGGLES_MODULE)
        model = importlib.import_module(FORM_MODEL_MODULE)
    except ImportError as exc:
        sys.exit(f"Attachment-Schritt fehlt ({exc}); --detector none nutzen")
    merge = getattr(toggles, ATTR_MERGE)
    attach = getattr(toggles, ATTR_ATTACH)
    checked_prefix: str = getattr(model, ATTR_CHECKED_PREFIX)
    unchecked_prefix: str = getattr(model, ATTR_UNCHECKED_PREFIX)

    def run(pdf_bytes: bytes, toggles_found: list[Any]) -> list[DetectedLine]:
        document_uuid = uuid4()
        lines: list[NewSourceLine] = extract_source_lines(pdf_bytes, document_uuid)
        attached, _ = attach(merge(lines), toggles_found, document_uuid)
        detected: list[DetectedLine] = []
        for line in attached:
            if line.line_text.startswith(checked_prefix):
                state = LineState.CHECKED
            elif line.line_text.startswith(unchecked_prefix):
                state = LineState.UNCHECKED
            else:
                continue
            detected.append(
                DetectedLine(
                    page=line.page, bbox=line.bbox, text=line.line_text, state=state
                )
            )
        return detected

    return run


def _print_box_table(by_family: dict[str, BoxScore], with_detector: bool) -> None:
    total = BoxScore()
    rows = sorted(by_family.items()) + [("gesamt", None)]
    header = (
        f"{'Familie':14} {'Label':>6} {'Erkannt':>8} {'TP':>5} {'Status?':>8} "
        f"{'FP':>5} {'Fehlt':>6} {'Prec':>6} {'Rec':>6}"
    )
    print(header)
    print("-" * len(header))
    for family, score in rows:
        if score is None:
            score = total
        else:
            total = total.add(score)
        if with_detector:
            print(
                f"{family:14} {score.labelled:6} {score.detected:8} "
                f"{score.true_positives:5} {len(score.wrong_state):8} "
                f"{len(score.false_positives):5} {len(score.misses):6} "
                f"{score.precision:6.3f} {score.recall:6.3f}"
            )
        else:
            print(
                f"{family:14} {score.labelled:6} {'-':>8} {'-':>5} {'-':>8} "
                f"{'-':>5} {'-':>6}"
            )


def _print_box_details(details: list[tuple[str, BoxScore]]) -> None:
    for name, score in details:
        if not (score.misses or score.false_positives or score.wrong_state):
            continue
        print(f"\n{name}")
        for text in score.misses:
            print(f"  FEHLT   {text}")
        for text in score.false_positives:
            print(f"  FP      {text}")
        for text in score.wrong_state:
            print(f"  STATUS  {text}")


def _print_label_stats(files: list[Path]) -> None:
    print()
    print(f"{'Tender / PDF':70} {'Seiten':>6} {'☒':>4} {'☐':>4}")
    for path in files:
        labels = load_labels(path)
        checked = sum(1 for line in labels.lines if line.state is LineState.CHECKED)
        unchecked = sum(1 for line in labels.lines if line.state is LineState.UNCHECKED)
        name = f"{labels.tender} / {Path(labels.pdf).name}"[:70]
        print(f"{name:70} {len(labels.labelled_pages):6} {checked:4} {unchecked:4}")


# --- facts ------------------------------------------------------------------------


class FactResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender: str
    key: str
    question: str
    gold: str
    answers: list[str]
    correct: list[bool]


def run_facts(args: argparse.Namespace) -> None:
    files = list_fact_files(args.labels_root)
    if not files:
        print(f"keine Fakten-Dateien unter {args.labels_root}")
        return
    retrieval = {
        FIELD_MODALITY: RetrievalModality(args.modality.upper()).value,
        FIELD_MULTI_QUERY: args.multi_query,
        FIELD_USE_BM25: args.bm25,
        FIELD_USE_CROSS_ENCODER: args.cross_encoder,
    }
    overrides = dict(item.split("=", 1) for item in args.project_map)
    results: list[FactResult] = []
    with httpx.Client(base_url=args.api, timeout=TURN_TIMEOUT_S) as client:
        projects = client.get(PATH_PROJECTS).raise_for_status().json()
        for path in files:
            facts = load_facts(path)
            project_uuid = overrides.get(facts.tender) or resolve_project(
                projects, facts.tender
            )
            if project_uuid is None:
                print(f"{facts.tender}: kein Projekt gefunden, --project-map setzen")
                continue
            labelled = [fact for fact in facts.facts if fact.is_labelled]
            print(
                f"{facts.tender}: {len(labelled)} Fakten gegen Projekt {project_uuid}"
            )
            answers: dict[str, list[str]] = {fact.key: [] for fact in labelled}
            for n in range(1, args.repeat + 1):
                conversation = _create_conversation(
                    client, project_uuid, facts.tender, n
                )
                for fact in labelled:
                    _send_turn(client, conversation, fact.question, retrieval)
                    answers[fact.key].append(
                        _last_assistant_message(client, conversation)
                    )
                    print(f"  [{n}/{args.repeat}] {fact.key}")
                if args.delete_conversations:
                    client.delete(PATH_CONVERSATION.format(uuid=conversation))
            for fact in labelled:
                gold = gold_items(fact.gold)
                correct = [
                    grade_yes_no(answer) == gold[0]
                    if fact.kind is FactKind.YES_NO
                    else grade_contains(answer, gold)
                    for answer in answers[fact.key]
                ]
                results.append(
                    FactResult(
                        tender=facts.tender,
                        key=fact.key,
                        question=fact.question,
                        gold="; ".join(gold),
                        answers=answers[fact.key],
                        correct=correct,
                    )
                )
    _print_fact_table(results, args.repeat)


def _create_conversation(
    client: httpx.Client, project_uuid: str, tender: str, n: int
) -> str:
    payload = {
        FIELD_PROMPT_TYPE: PromptType.PROJECT_CHAT.value,
        FIELD_PROJECT_UUID: project_uuid,
        FIELD_TITLE: CONVERSATION_TITLE.format(tender=tender, n=n),
    }
    response = client.post(PATH_CONVERSATIONS, json=payload).raise_for_status()
    return str(response.json()[FIELD_CONVERSATION_UUID])


def _send_turn(
    client: httpx.Client, conversation: str, question: str, retrieval: dict[str, Any]
) -> None:
    payload = {FIELD_CONTENT: question, FIELD_RETRIEVAL: retrieval}
    with client.stream(
        "POST", PATH_TURN.format(uuid=conversation), json=payload
    ) as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line == f"{SSE_EVENT_PREFIX}{SSE_EVENT_DONE}":
                break


def _last_assistant_message(client: httpx.Client, conversation: str) -> str:
    messages = (
        client.get(PATH_MESSAGES.format(uuid=conversation)).raise_for_status().json()
    )
    for message in reversed(messages):
        if message[FIELD_KIND] == MessageKind.ASSISTANT.value and message.get(
            FIELD_CONTENT
        ):
            return str(message[FIELD_CONTENT])
    return ""


def _print_fact_table(results: list[FactResult], repeat: int) -> None:
    rows: list[tuple[str, list[FactResult]]] = []
    for tender in sorted({r.tender for r in results}):
        rows.append((tender, [r for r in results if r.tender == tender]))
    rows.append(("gesamt", results))
    print()
    runs = f"{repeat}/{repeat}"
    header = f"{'Tender':28} {'Fakten':>6} {runs:>6} {'teils':>6} {'falsch':>6}"
    print(header)
    print("-" * len(header))
    for name, group in rows:
        full = sum(1 for r in group if all(r.correct))
        none = sum(1 for r in group if not any(r.correct))
        print(
            f"{name:28} {len(group):6} {full:6} {len(group) - full - none:6} {none:6}"
        )
    for result in results:
        if all(result.correct):
            continue
        print(f"\n{result.tender} · {result.key} · Gold: {result.gold}")
        print(f"  Frage: {result.question}")
        for n, (answer, ok) in enumerate(zip(result.answers, result.correct), start=1):
            print(f"  [{n}] {'OK ' if ok else 'XX '} {answer}")


# --- cli --------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the Formblatt labels.")
    parser.add_argument("--boxes", action="store_true", help="score box labels offline")
    parser.add_argument(
        "--facts", action="store_true", help="ask facts via the chat API"
    )
    parser.add_argument(
        "--detector", default=DEFAULT_DETECTOR, help="module:function or none"
    )
    parser.add_argument("--labels-root", type=Path, default=DEFAULT_LABELS_ROOT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument(
        "--modality",
        default=RetrievalModality.SIMPLE.value.lower(),
        choices=["simple", "plus"],
    )
    parser.add_argument("--bm25", action="store_true")
    parser.add_argument("--multi-query", action="store_true")
    parser.add_argument("--cross-encoder", action="store_true")
    parser.add_argument(
        "--project-map", action="append", default=[], metavar="TENDER=UUID"
    )
    parser.add_argument("--delete-conversations", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not (args.boxes or args.facts):
        sys.exit("--boxes und/oder --facts angeben")
    if args.boxes:
        run_boxes(args.labels_root, args.corpus, args.detector)
    if args.facts:
        run_facts(args)


if __name__ == "__main__":
    main()
