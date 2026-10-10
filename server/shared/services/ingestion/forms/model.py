from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.models.form_field import NewFormField
from shared.models.source_line import NewSourceLine

# Contract literals of the form source lines, read back by chunk_form and the UI.
FORM_SECTION_PREFIX = "## "
LABEL_SEPARATOR = ": "
CHECKED = "ja"
UNCHECKED = "nein"


class FormExtraction(BaseModel):
    """One pass over a form: reading-order source lines and the structured fields."""

    model_config = ConfigDict(extra="forbid")

    lines: list[NewSourceLine]
    fields: list[NewFormField]


def section_heading(section: str) -> str:
    return f"{FORM_SECTION_PREFIX}{section}"


def field_line(label: str, value: str) -> str:
    return f"{label}{LABEL_SEPARATOR}{value}"
