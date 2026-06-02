"""Common ingestion stage: PDF bytes to per-line SourceLine rows.

Text is extracted with poppler's `pdftotext -bbox-layout`, which renders the page's content
*and* its AcroForm field appearances (filled-in dates, checkboxes, free-text fields) and emits
word/line geometry as XHTML. This matters for the construction forms in the corpus, whose
contractual data lives in fillable form fields that the PDF content stream alone does not carry;
it also reconstructs word spacing that a raw content-stream extractor drops. Each `<line>` becomes
one SourceLine, enumerated into a single gap-free `line_id` that runs across pages, so the same
integer is the stable reference the LV extraction segments on (INGESTION.md)."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from uuid import UUID

from shared.models.source_line import NewSourceLine

# poppler invocation: read the PDF from stdin, write bbox XHTML to stdout.
PDFTOTEXT = "pdftotext"
ARG_BBOX_LAYOUT = "-bbox-layout"
STDIO = "-"

# pdftotext XHTML tags (local names; the document carries an xhtml namespace) and geometry attrs.
TAG_PAGE = "page"
TAG_LINE = "line"
TAG_WORD = "word"
ATTR_XMIN = "xMin"
ATTR_YMIN = "yMin"
ATTR_XMAX = "xMax"
ATTR_YMAX = "yMax"


def extract_source_lines(pdf_bytes: bytes, document_uuid: UUID) -> list[NewSourceLine]:
    """Extract every visual line of a PDF as a NewSourceLine, with a global line_id."""
    result = subprocess.run(
        [PDFTOTEXT, ARG_BBOX_LAYOUT, STDIO, STDIO],
        input=pdf_bytes,
        capture_output=True,
        check=True,
    )
    return parse_bbox_layout(result.stdout, document_uuid)


def parse_bbox_layout(xhtml: bytes, document_uuid: UUID) -> list[NewSourceLine]:
    """Parse `pdftotext -bbox-layout` XHTML into NewSourceLine rows.

    One row per non-empty `<line>`; bbox is (xMin, yMin, xMax, yMax) in top-origin coordinates;
    page is 1-based; line_id is a single counter across pages."""
    root = ET.fromstring(xhtml)
    lines: list[NewSourceLine] = []
    line_id = 0
    for page_number, page in enumerate(_find(root, TAG_PAGE), start=1):
        for line in _find(page, TAG_LINE):
            words = [(word.text or "").strip() for word in _find(line, TAG_WORD)]
            text = " ".join(word for word in words if word)
            if not text:
                continue
            lines.append(
                NewSourceLine(
                    document_uuid=document_uuid,
                    line_id=line_id,
                    page=page_number,
                    bbox=(
                        float(line.get(ATTR_XMIN, 0.0)),
                        float(line.get(ATTR_YMIN, 0.0)),
                        float(line.get(ATTR_XMAX, 0.0)),
                        float(line.get(ATTR_YMAX, 0.0)),
                    ),
                    line_text=text,
                )
            )
            line_id += 1
    return lines


def _find(element: ET.Element, local_name: str) -> list[ET.Element]:
    """All descendants whose tag local name matches, ignoring the xhtml namespace prefix."""
    return [e for e in element.iter() if e.tag.rsplit("}", 1)[-1] == local_name]
