"""Label files: Pydantic models and atomic JSON read/write.

One `FormLabels` file per labelled PDF (`labels/<tender>/<stem>.json`) and one
`FactFile` per tender (`facts/<tender>.json`). A line label stores page, bbox and text
of the extracted line, never a line id, so a later merge of marginal tokens (which
renumbers lines) still matches by geometry and text.
"""

from __future__ import annotations

import json
import os
import tempfile
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

LABELS_DIR = "labels"
FACTS_DIR = "facts"
JSON_SUFFIX = ".json"


class LineState(StrEnum):
    NONE = "none"
    UNCHECKED = "unchecked"
    CHECKED = "checked"


class PdfKind(StrEnum):
    """`detect_form_kind` at label time (`flattened` is a zero-field PDF whose footer
    or filename names a known Formblatt)."""

    XFA = "xfa"
    ACROFORM = "acroform"
    FLATTENED = "flattened"


class LineLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    bbox: tuple[float, float, float, float]
    text: str
    state: LineState


class FormLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender: str
    pdf: str
    form_id: str | None
    kind: PdfKind
    labelled_pages: list[int] = []
    lines: list[LineLabel] = []

    def page_lines(self, page: int) -> list[LineLabel]:
        return [line for line in self.lines if line.page == page]

    def with_page(self, page: int, lines: list[LineLabel]) -> FormLabels:
        """The labels with `page` replaced by `lines` (states other than none only) and
        marked as labelled."""
        kept = [line for line in self.lines if line.page != page]
        new = [line for line in lines if line.state is not LineState.NONE]
        pages = sorted(set(self.labelled_pages) | {page})
        return self.model_copy(update={"lines": kept + new, "labelled_pages": pages})


class FactKind(StrEnum):
    YES_NO = "yes_no"
    VALUE = "value"
    LIST = "list"


class FactSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf: str
    page: int
    section: str | None = None


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    question: str
    kind: FactKind
    gold: str | list[str] | None = None
    source: FactSource | None = None

    @property
    def is_labelled(self) -> bool:
        return self.gold not in (None, "", [])


class FactFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender: str
    facts: list[Fact] = []


def labels_path(root: Path, tender: str, stem: str) -> Path:
    return root / LABELS_DIR / tender / f"{stem}{JSON_SUFFIX}"


def facts_path(root: Path, tender: str) -> Path:
    return root / FACTS_DIR / f"{tender}{JSON_SUFFIX}"


def load_labels(path: Path) -> FormLabels:
    return FormLabels.model_validate_json(path.read_text(encoding="utf-8"))


def save_labels(path: Path, labels: FormLabels) -> None:
    _write_atomic(path, labels)


def load_facts(path: Path) -> FactFile:
    return FactFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_facts(path: Path, facts: FactFile) -> None:
    _write_atomic(path, facts)


def list_label_files(root: Path) -> list[Path]:
    base = root / LABELS_DIR
    if not base.is_dir():
        return []
    return sorted(base.glob(f"*/*{JSON_SUFFIX}"))


def list_fact_files(root: Path) -> list[Path]:
    base = root / FACTS_DIR
    if not base.is_dir():
        return []
    return sorted(base.glob(f"*{JSON_SUFFIX}"))


def _write_atomic(path: Path, model: BaseModel) -> None:
    """Write to a temp file in the target directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2
    )
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
