"""Page rendering with pdf2image (poppler), the renderer of the production thumbnails.

Rendered pages are cached as PNG under `eval/forms/.cache/<sha1 of path>/<page>.png`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pdf2image import convert_from_path

CACHE_DIR = ".cache"
RENDER_DPI = 110
PNG_SUFFIX = ".png"


def render_page(
    pdf_path: Path, page: int, cache_root: Path, dpi: int = RENDER_DPI
) -> Path:
    """The PNG of one page (1-based), rendered on first use."""
    target = cache_root / CACHE_DIR / _key(pdf_path) / f"{page}{PNG_SUFFIX}"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    images = convert_from_path(str(pdf_path), dpi=dpi, first_page=page, last_page=page)
    images[0].save(target)
    return target


def _key(pdf_path: Path) -> str:
    return hashlib.sha1(str(pdf_path.resolve()).encode("utf-8")).hexdigest()
