from __future__ import annotations

import io
import shutil

import pytest

pytest.importorskip("pdf2image")
if shutil.which("pdftoppm") is None and shutil.which("pdftocairo") is None:
    pytest.skip("poppler (pdftoppm/pdftocairo) not installed", allow_module_level=True)

from PIL import Image  # noqa: E402

from shared.services.ingestion.thumbnails import (  # noqa: E402
    THUMBNAIL_CONTENT_TYPE,
    THUMBNAIL_WIDTH,
    render_thumbnails,
)

JPEG_MAGIC = b"\xff\xd8\xff"


def _pdf(*sizes: tuple[int, int]) -> bytes:
    """A valid PDF with one page per given (width, height), via Pillow."""
    pages = [Image.new("RGB", size, "white") for size in sizes]
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def test_renders_one_thumbnail_per_page() -> None:
    pages = render_thumbnails(_pdf((300, 400), (600, 300)))

    assert [p.page_number for p in pages] == [1, 2]
    for page in pages:
        assert page.width == THUMBNAIL_WIDTH  # downscaled to the target width
        assert page.height > 0
        assert page.content_type == THUMBNAIL_CONTENT_TYPE
        assert page.data.startswith(JPEG_MAGIC)


def test_preserves_aspect_ratio() -> None:
    [page] = render_thumbnails(_pdf((300, 600)))
    # 300x600 source -> width 400 -> height ~800.
    assert page.width == THUMBNAIL_WIDTH
    assert page.height == pytest.approx(THUMBNAIL_WIDTH * 2, rel=0.05)
