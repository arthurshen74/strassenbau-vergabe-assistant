from __future__ import annotations

from scripts.eval_form_labels import (
    DetectedLine,
    grade_contains,
    grade_yes_no,
    lines_match,
    resolve_project,
    score_boxes,
)
from scripts.form_labeler.store import LineLabel, LineState

LABEL = LineLabel(
    page=3,
    bbox=(104.881, 482.283, 468.231, 495.103),
    text=(
        "Nebenangebote sind nicht zugelassen; "
        "Nr. 4 der Teilnahmebedingungen gilt nicht."
    ),
    state=LineState.CHECKED,
)


def test_merged_line_matches_the_original_label_line() -> None:
    merged = f"[x] 6.1 {LABEL.text}"
    assert lines_match(LABEL, 3, (62.362, 482.283, 468.231, 495.103), merged)


def test_glyph_merged_label_matches_detector_line_without_glyph() -> None:
    label = LineLabel(
        page=3,
        bbox=(92.1, 444.3, 182.1, 457.1),
        text="X nicht zugelassen.",
        state=LineState.CHECKED,
    )
    assert lines_match(label, 3, (92.1, 444.3, 182.1, 457.1), "[x] nicht zugelassen.")


def test_other_line_or_page_does_not_match() -> None:
    other = (
        "[ ] 6.2 Nebenangebote sind zugelassen (s. auch Nr. 4 der Teilnahmebedingungen)"
    )
    assert not lines_match(LABEL, 3, (104.881, 508.927, 516.051, 521.747), other)
    assert not lines_match(LABEL, 2, LABEL.bbox, f"[x] {LABEL.text}")


def test_score_boxes_counts_states_and_misses() -> None:
    detected = [
        DetectedLine(
            page=3, bbox=LABEL.bbox, text=f"[ ] {LABEL.text}", state=LineState.UNCHECKED
        ),
        DetectedLine(
            page=3, bbox=(0, 0, 1, 1), text="[x] extra", state=LineState.CHECKED
        ),
    ]
    missed = LineLabel(
        page=4, bbox=(0, 0, 1, 1), text="fehlt", state=LineState.UNCHECKED
    )
    score = score_boxes([LABEL, missed], detected)
    assert (score.labelled, score.detected, score.true_positives) == (2, 2, 0)
    assert len(score.wrong_state) == 1
    assert len(score.false_positives) == 1
    assert len(score.misses) == 1


def test_yes_no_grader_takes_the_first_token() -> None:
    assert grade_yes_no("Ja.") == "ja"
    assert grade_yes_no("Nein, Nebenangebote sind nicht zugelassen.") == "nein"
    assert grade_yes_no("Ja, aber nur eingeschränkt") == "ja"
    assert grade_yes_no("Laut Formblatt sind sie nicht zugelassen.") is None


def test_contains_grader_is_case_insensitive_over_every_item() -> None:
    assert grade_contains("Die Frist endet am 31.12.2026.", ["31.12.2026"])
    assert grade_contains("Preis und Qualität.", ["preis", "Qualität"])
    assert not grade_contains("Nur der Preis.", ["Preis", "Qualität"])


def test_resolve_project_by_vergabe_id_or_name() -> None:
    projects = [
        {"project_uuid": "u1", "project_name": "Brücke", "vergabe_id": "NOO-2026-0304"},
        {"project_uuid": "u2", "project_name": "O-222-2026-00001", "vergabe_id": None},
    ]
    assert resolve_project(projects, "NOO-2026-0304_10BW62-1") == "u1"
    assert resolve_project(projects, "O-222-2026-00001") == "u2"
    assert resolve_project(projects, "WNAB-SB7-12-2026") is None
