from __future__ import annotations

import io
import zipfile

from shared.models.enums import DocumentType
from shared.services.project_service import (
    UploadInput,
    _classify_document_type,
    _count_pdf_pages,
    _expand_zip,
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_expand_zip_flattens_paths_and_skips_junk() -> None:
    data = _zip(
        {
            "a.pdf": b"x",
            "sub/dir/b.txt": b"y",  # nested -> basename only
            "__MACOSX/c": b"z",  # macOS junk -> skipped
            ".DS_Store": b"q",  # dotfile -> skipped
        }
    )
    out = _expand_zip(data)
    assert sorted(u.file_name for u in out) == ["a.pdf", "b.txt"]


def test_count_pdf_pages_non_pdf_is_zero() -> None:
    assert _count_pdf_pages(UploadInput("notes.txt", "text/plain", b"hello")) == 0


def test_classify_document_type_lv_filename() -> None:
    assert _classify_document_type("Projekt_LV1.pdf") == DocumentType.LV_DOCUMENT
    assert _classify_document_type("Projekt_LV.pdf") == DocumentType.LV_DOCUMENT


def test_classify_document_type_prose_for_anything_else() -> None:
    assert _classify_document_type("Projekt_LV1.txt") == DocumentType.PROSE_DOCUMENT
    assert _classify_document_type("anhang.pdf") == DocumentType.PROSE_DOCUMENT
