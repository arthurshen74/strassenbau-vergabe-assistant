"""Common ingestion stage: PDF bytes to per-line SourceLine rows.

pdfplumber's `extract_text_lines()` yields one record per visual line (unlike `page.lines`,
which is vector graphics). We enumerate those records into a single gap-free `line_id` that
runs across pages, so the same integer doubles as the stable reference the LV extraction
segments on. The verbatim text persisted here is the canonical source the rest of the
pipeline slices from (INGESTION.md)."""

from __future__ import annotations

import io
from uuid import UUID

import pdfplumber

from shared.models.source_line import NewSourceLine

# pdfplumber extract_text_lines() record keys.
KEY_TEXT = "text"
KEY_X0 = "x0"
KEY_X1 = "x1"
KEY_TOP = "top"
KEY_BOTTOM = "bottom"

# We need the line text and its bounding box, not per-character detail.
RETURN_CHARS = False


def extract_source_lines(pdf_bytes: bytes, document_uuid: UUID) -> list[NewSourceLine]:
    """Extract every visual line of a PDF as a NewSourceLine, with a global line_id.

    bbox is (x0, top, x1, bottom) in pdfplumber's top-origin coordinates; page is 1-based."""
    lines: list[NewSourceLine] = []
    line_id = 0
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for line in page.extract_text_lines(return_chars=RETURN_CHARS):
                lines.append(
                    NewSourceLine(
                        document_uuid=document_uuid,
                        line_id=line_id,
                        page=page_number,
                        bbox=(
                            line[KEY_X0],
                            line[KEY_TOP],
                            line[KEY_X1],
                            line[KEY_BOTTOM],
                        ),
                        line_text=line[KEY_TEXT],
                    )
                )
                line_id += 1
    return lines
