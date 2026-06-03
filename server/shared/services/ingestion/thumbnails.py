"""Render PDF pages to per-page thumbnail images.

Every ingested PDF gets one thumbnail per page (INGESTION.md). pdf2image rasterises each page
(poppler under the hood) at a fixed DPI, encode as JPEG, and report the stored dimensions.
Rendering is CPU/IO bound and synchronous, so the service offloads it to a thread."""

from __future__ import annotations

import io
from dataclasses import dataclass

from pdf2image import convert_from_bytes

# Rasterisation resolution; poppler renders each page at this DPI preserving aspect ratio.
THUMBNAIL_DPI = 200
THUMBNAIL_FORMAT = "JPEG"
THUMBNAIL_CONTENT_TYPE = "image/jpeg"
JPEG_QUALITY = 80
RGB_MODE = "RGB"


@dataclass(frozen=True)
class RenderedPage:
    """One rendered page thumbnail: its 1-based page number, encoded bytes, and dimensions."""

    page_number: int
    data: bytes
    width: int
    height: int
    content_type: str


def render_thumbnails(pdf_bytes: bytes) -> list[RenderedPage]:
    """Render every page of a PDF to a downscaled JPEG thumbnail, page numbers 1-based."""
    images = convert_from_bytes(pdf_bytes, dpi=THUMBNAIL_DPI)
    pages: list[RenderedPage] = []
    for page_number, image in enumerate(images, start=1):
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
