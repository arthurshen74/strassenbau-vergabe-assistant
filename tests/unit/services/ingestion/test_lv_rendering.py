from __future__ import annotations

from uuid import uuid4

from shared.models.source_line import SourceLine
from shared.services.ingestion.lv.rendering import LINE_ID_SEP, render_line_numbered


def _line(line_id: int, page: int, text: str) -> SourceLine:
    return SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=uuid4(),
        line_id=line_id,
        page=page,
        bbox=(0, 0, 1, 1),
        line_text=text,
    )


def test_strips_anchor_furniture_and_keeps_original_line_ids() -> None:
    lines = [
        _line(0, 1, "Projektnummer: P0372026 Datum: 01.01.2026"),
        _line(1, 1, "LEISTUNGSVERZEICHNIS"),
        _line(2, 1, "1.1 Oberboden abtragen"),
        _line(3, 1, "Dateiname: x.pdf Seite:1 von 2"),
        _line(4, 2, "1.2 Mutterboden andecken"),
    ]

    rendered, kept = render_line_numbered(lines)

    assert kept == [2, 4]  # anchors dropped, content kept
    assert rendered == f"2{LINE_ID_SEP}1.1 Oberboden abtragen\n4{LINE_ID_SEP}1.2 Mutterboden andecken"


def test_strips_text_repeating_across_pages() -> None:
    header = "Ordnungszahl Menge Einheit Einheitspreis Gesamtbetrag"
    lines = [_line(i, page, header) for i, page in enumerate([1, 2, 3])]
    lines.append(_line(3, 1, "1.1 unique content line"))

    _, kept = render_line_numbered(lines)

    assert kept == [3]  # the header repeating on 3 pages is furniture; content survives
