from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.form_labeler.store import (
    Fact,
    FactFile,
    FactKind,
    FactSource,
    FormLabels,
    LineLabel,
    LineState,
    PdfKind,
    load_facts,
    load_labels,
    save_facts,
    save_labels,
)


def _labels() -> FormLabels:
    return FormLabels(
        tender="NOO-2026-0304_10BW62-1",
        pdf="Heftung 1/HVA_B_StB_111.pdf",
        form_id="HVA B-StB 111",
        kind=PdfKind.FLATTENED,
        labelled_pages=[3],
        lines=[
            LineLabel(
                page=3,
                bbox=(104.9, 482.3, 468.2, 495.1),
                text="Nebenangebote sind nicht zugelassen",
                state=LineState.CHECKED,
            )
        ],
    )


def test_labels_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "labels" / "t" / "x.json"
    save_labels(path, _labels())
    assert load_labels(path) == _labels()


def test_facts_round_trip(tmp_path: Path) -> None:
    facts = FactFile(
        tender="t",
        facts=[
            Fact(
                key="nebenangebote_zugelassen",
                question="Sind Nebenangebote zugelassen?",
                kind=FactKind.YES_NO,
                gold="nein",
                source=FactSource(pdf="a.pdf", page=3, section="6 Nebenangebote"),
            ),
            Fact(key="offen", question="?", kind=FactKind.LIST),
        ],
    )
    path = tmp_path / "facts" / "t.json"
    save_facts(path, facts)
    loaded = load_facts(path)
    assert loaded == facts
    assert [fact.is_labelled for fact in loaded.facts] == [True, False]


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FormLabels.model_validate({**_labels().model_dump(mode="json"), "line_id": 1})
    with pytest.raises(ValidationError):
        LineLabel.model_validate(
            {"page": 1, "bbox": [0, 0, 1, 1], "text": "x", "state": "checked", "id": 1}
        )


def test_atomic_write_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    save_labels(path, _labels())
    save_labels(path, _labels().with_page(4, []))
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]
    assert load_labels(path).labelled_pages == [3, 4]


def test_with_page_replaces_the_page_and_drops_none() -> None:
    new = [
        LineLabel(page=3, bbox=(0, 0, 1, 1), text="a", state=LineState.NONE),
        LineLabel(page=3, bbox=(0, 2, 1, 3), text="b", state=LineState.UNCHECKED),
    ]
    updated = _labels().with_page(3, new)
    assert [line.text for line in updated.lines] == ["b"]
    assert updated.labelled_pages == [3]
