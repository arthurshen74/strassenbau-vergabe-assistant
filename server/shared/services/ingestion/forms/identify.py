"""Formblatt identification from the printed page footer.

Every HVA B-StB form prints `NNN HVA B-StB <Titel> MM-YY` in the footer of every page,
so the number is read from the text of the first two pages. A variant digit (`104.1`)
is not part of the Formblatt key. Only the HVA pattern is known to be reliable; VHB and
WSV forms print no usable number and stay filename-based.
"""

from __future__ import annotations

import re
import subprocess

from shared.services.ingestion.extraction import PDFTOTEXT, STDIO
from shared.services.ingestion.forms.role import FormFamily

ARG_FIRST_PAGE = "-f"
ARG_LAST_PAGE = "-l"
IDENTIFY_PAGES = 2

FOOTER_HVA = re.compile(
    r"^\s*(\d{3})(?:\.\d)?\s+HVA\s*B-StB\b", re.MULTILINE | re.IGNORECASE
)


def identify_formblatt(pdf_bytes: bytes) -> tuple[FormFamily, str] | None:
    """(family, number) printed in the footer of the first pages, else None. Bytes
    that pdftotext cannot read yield None; `detect_form_kind` reports them."""
    try:
        result = subprocess.run(
            [
                PDFTOTEXT,
                ARG_FIRST_PAGE,
                "1",
                ARG_LAST_PAGE,
                str(IDENTIFY_PAGES),
                STDIO,
                STDIO,
            ],
            input=pdf_bytes,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    return identify_from_text(result.stdout.decode("utf-8", errors="replace"))


def identify_from_text(text: str) -> tuple[FormFamily, str] | None:
    match = FOOTER_HVA.search(text)
    if match is None:
        return None
    return FormFamily.HVA_B_STB, match.group(1)
