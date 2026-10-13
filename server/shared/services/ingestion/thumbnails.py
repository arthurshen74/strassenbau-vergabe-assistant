"""Render PDF pages to per-page thumbnail images.

Every ingested PDF gets one thumbnail per page (INGESTION.md). pdf2image rasterises
pages (poppler under the hood) at a fixed DPI, encode as JPEG, and report the stored
dimensions. Rendering is CPU/IO bound and synchronous, so the service offloads it to a
thread, one page range at a time: a whole-document render would hold every decoded page
in memory at once and report no progress until the last page."""

from __future__ import annotations

import io
from dataclasses import dataclass

from pdf2image import convert_from_bytes, pdfinfo_from_bytes

# Rasterisation resolution; poppler renders each page at this DPI preserving aspect
# ratio.
THUMBNAIL_DPI = 200
THUMBNAIL_FORMAT = "JPEG"
THUMBNAIL_CONTENT_TYPE = "image/jpeg"
JPEG_QUALITY = 80
RGB_MODE = "RGB"

# pdfinfo output key holding the page count.
PDFINFO_PAGES_KEY = "Pages"


@dataclass(frozen=True)
class RenderedPage:
    """One rendered page thumbnail: its 1-based page number, encoded bytes, and
    dimensions."""

    page_number: int
    data: bytes
    width: int
    height: int
    content_type: str


def count_pages(pdf_bytes: bytes) -> int:
    """Page count as poppler sees it, so it matches what `render_pages` will render."""
    return int(pdfinfo_from_bytes(pdf_bytes)[PDFINFO_PAGES_KEY])


def render_pages(
    pdf_bytes: bytes, first_page: int, last_page: int
) -> list[RenderedPage]:
    """Render the inclusive 1-based page range to downscaled JPEG thumbnails."""
    images = convert_from_bytes(
        pdf_bytes, dpi=THUMBNAIL_DPI, first_page=first_page, last_page=last_page
    )
    pages: list[RenderedPage] = []
    for page_number, image in enumerate(images, start=first_page):
        rgb = image.convert(RGB_MODE)  # JPEG has no alpha channel
        buffer = io.BytesIO()
        rgb.save(buffer, format=THUMBNAIL_FORMAT, quality=JPEG_QUALITY)
        pages.append(
            RenderedPage(
                page_number=page_number,
                data=buffer.getvalue(),
                width=rgb.width,
                height=rgb.height,
                content_type=THUMBNAIL_CONTENT_TYPE,
            )
        )
    return pages
