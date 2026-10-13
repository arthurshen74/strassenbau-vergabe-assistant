"""Contract of the form source lines shared by every form reader.

Whatever kind a form is (XFA, AcroForm, flattened), its readers emit the same line
shapes: `## <section>` headings, `label: value` for filled fields, `[x] <text>` /
`[ ] <text>` for options, and untouched static prose. `chunk_form` reads these markers
back; the UI reads `form_fields`, never the line text.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.models.form_field import NewFormField
from shared.models.source_line import NewSourceLine

# Contract literals of the form source lines, read back by chunk_form.
FORM_SECTION_PREFIX = "## "
LABEL_SEPARATOR = ": "
OPTION_CHECKED_PREFIX = "[x] "
OPTION_UNCHECKED_PREFIX = "[ ] "
NO_OPTION_CHECKED = "keine Option angekreuzt"

# `form_fields.value` vocabulary of a toggle.
CHECKED = "ja"
UNCHECKED = "nein"


class Toggle(BaseModel):
    """A checkbox or radio option located on a page: its square (top-origin points),
    its state, and the reader's own label, used only when no printed line is found."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int
    bbox: tuple[float, float, float, float]
    checked: bool
    label: str | None = None


class FormExtraction(BaseModel):
    """One pass over a form: reading-order source lines, the structured fields, and
    the toggle and furniture counts of the geometric readers (zero for XFA)."""

    model_config = ConfigDict(extra="forbid")

    lines: list[NewSourceLine]
    fields: list[NewFormField]
    toggles: int = 0
    checked: int = 0
    unresolved: int = 0
    furniture: int = 0


def section_heading(section: str) -> str:
    return f"{FORM_SECTION_PREFIX}{section}"


def field_line(label: str, value: str) -> str:
    return f"{label}{LABEL_SEPARATOR}{value}"


def option_line(label: str, checked: bool) -> str:
    prefix = OPTION_CHECKED_PREFIX if checked else OPTION_UNCHECKED_PREFIX
    return f"{prefix}{label}"


def is_option_line(text: str) -> bool:
    return text.startswith((OPTION_CHECKED_PREFIX, OPTION_UNCHECKED_PREFIX))


def option_label(text: str) -> str:
    """The printed text of an option line, without its marker."""
    return text[len(OPTION_CHECKED_PREFIX) :]
