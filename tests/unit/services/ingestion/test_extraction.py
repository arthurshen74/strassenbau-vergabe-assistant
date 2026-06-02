from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from shared.services.ingestion import extraction
from shared.services.ingestion.extraction import extract_source_lines, parse_bbox_layout

# A minimal pdftotext -bbox-layout document: xhtml namespace + DOCTYPE, two pages, a multi-word
# line (spacing), a single-value line (a form field), and an empty line (must be skipped).
SAMPLE_XHTML = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "x.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>t</title></head>
<body><doc>
<page width="595" height="842">
  <block xMin="10" yMin="20" xMax="200" yMax="30">
    <line xMin="10" yMin="20" xMax="200" yMax="30">
      <word xMin="10" yMin="20" xMax="50" yMax="30">Mit</word>
      <word xMin="55" yMin="20" xMax="120" yMax="30">der</word>
      <word xMin="125" yMin="20" xMax="200" yMax="30">Ausführung</word>
    </line>
  </block>
  <block xMin="10" yMin="40" xMax="80" yMax="50">
    <line xMin="10" yMin="40" xMax="80" yMax="50">
      <word xMin="10" yMin="40" xMax="80" yMax="50">27.07.2026</word>
    </line>
    <line xMin="10" yMin="60" xMax="80" yMax="70"></line>
  </block>
</page>
<page width="595" height="842">
  <block xMin="12" yMin="22" xMax="84" yMax="33">
    <line xMin="12" yMin="22" xMax="84" yMax="33">
      <word xMin="12" yMin="22" xMax="84" yMax="33">Seite2</word>
    </line>
  </block>
</page>
</doc></body></html>""".encode("utf-8")


def test_parse_groups_words_numbers_lines_and_maps_bbox() -> None:
    doc = uuid4()
    lines = parse_bbox_layout(SAMPLE_XHTML, doc)

    assert [line.line_id for line in lines] == [0, 1, 2]  # gap-free across pages, empty skipped
    assert [line.page for line in lines] == [1, 1, 2]  # 1-based
    assert [line.line_text for line in lines] == [
        "Mit der Ausführung",  # words joined with single spaces, umlaut preserved
        "27.07.2026",
        "Seite2",
    ]
    assert lines[0].bbox == (10.0, 20.0, 200.0, 30.0)  # (xMin, yMin, xMax, yMax)
    assert all(line.document_uuid == doc for line in lines)


def test_extract_source_lines_pipes_pdf_through_pdftotext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Result:
        stdout = SAMPLE_XHTML

    def fake_run(cmd: list[str], *, input: bytes, capture_output: bool, check: bool) -> _Result:
        captured["cmd"] = cmd
        captured["input"] = input
        return _Result()

    monkeypatch.setattr(extraction.subprocess, "run", fake_run)

    doc = uuid4()
    lines = extract_source_lines(b"%PDF-bytes", doc)

    assert captured["cmd"][0] == "pdftotext"
    assert "-bbox-layout" in captured["cmd"]
    assert captured["input"] == b"%PDF-bytes"
    assert [line.line_text for line in lines] == [
        "Mit der Ausführung",
        "27.07.2026",
        "Seite2",
    ]
