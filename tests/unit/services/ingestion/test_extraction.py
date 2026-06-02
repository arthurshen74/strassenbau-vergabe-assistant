from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from shared.services.ingestion import extraction
from shared.services.ingestion.extraction import extract_source_lines


class _FakePage:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self._lines = lines

    def extract_text_lines(self, return_chars: bool = True) -> list[dict[str, Any]]:
        return self._lines


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _record(text: str, x0: float, top: float, x1: float, bottom: float) -> dict[str, Any]:
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


def test_line_id_is_global_and_pages_are_one_based(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        _FakePage([_record("a", 1, 2, 3, 4), _record("b", 5, 6, 7, 8)]),
        _FakePage([_record("c", 9, 10, 11, 12)]),
    ]
    monkeypatch.setattr(extraction.pdfplumber, "open", lambda *_a, **_k: _FakePdf(pages))

    lines = extract_source_lines(b"pdf", uuid4())

    assert [line.line_id for line in lines] == [0, 1, 2]  # gap-free across pages
    assert [line.page for line in lines] == [1, 1, 2]  # 1-based
    assert [line.line_text for line in lines] == ["a", "b", "c"]
    assert lines[0].bbox == (1, 2, 3, 4)  # (x0, top, x1, bottom)


def test_blank_pages_yield_no_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [_FakePage([]), _FakePage([_record("only", 0, 0, 1, 1)])]
    monkeypatch.setattr(extraction.pdfplumber, "open", lambda *_a, **_k: _FakePdf(pages))

    lines = extract_source_lines(b"pdf", uuid4())

    assert len(lines) == 1
    assert lines[0].page == 2 and lines[0].line_id == 0
