from __future__ import annotations

from uuid import uuid4

from shared.models.source_line import NewSourceLine
from shared.services.ingestion.forms.furniture import (
    FURNITURE_Y_TOLERANCE,
    furniture_key,
    remove_furniture,
)

DOC = uuid4()
FOOTER = "111 HVA B-StB Vorlage Aufforderung zur Angebotsabgabe 03-23"


def _line(text: str, page: int, y: float, x0: float = 62.4) -> NewSourceLine:
    return NewSourceLine(
        document_uuid=DOC,
        line_id=0,
        page=page,
        bbox=(x0, y, x0 + 200, y + 12.8),
        line_text=text,
    )


def _page(page: int, *content: str) -> list[NewSourceLine]:
    return [
        *(_line(text, page, 100.0 + 20 * i) for i, text in enumerate(content)),
        _line(FOOTER, page, 785.1),
        _line(f"Seite {page}", page, 785.1, x0=504.6),
    ]


def _texts(lines: list[NewSourceLine]) -> list[str]:
    return [line.line_text for line in lines]


def test_repeated_footer_keeps_its_first_occurrence() -> None:
    lines = [*_page(1, "Kopf"), *_page(2, "6 Nebenangebote"), *_page(3, "Anlagen")]

    kept, removed = remove_furniture(lines)

    assert _texts(kept) == [
        "Kopf",
        FOOTER,
        "Seite 1",
        "6 Nebenangebote",
        "Anlagen",
    ]
    assert removed == 4


def test_digits_are_collapsed_in_the_key() -> None:
    assert furniture_key("Seite 3 von 11") == furniture_key(" Seite  10 von 4 ")
    assert furniture_key("131 HVA B-StB 03-23") == "# HVA B-StB #-#"


def test_single_page_has_no_furniture() -> None:
    kept, removed = remove_furniture(_page(1, "Kopf"))
    assert len(kept) == 3 and removed == 0


def test_same_text_at_different_heights_is_content() -> None:
    lines = [
        _line("Sonstiges:", 1, 120.0),
        _line("Sonstiges:", 2, 400.0),
        _line("Sonstiges:", 3, 650.0),
    ]
    assert remove_furniture(lines) == (lines, 0)


def test_height_tolerance_boundary() -> None:
    inside = [
        _line("Kopfzeile", 1, 60.0),
        _line("Kopfzeile", 2, 60.0 + FURNITURE_Y_TOLERANCE),
    ]
    outside = [
        _line("Kopfzeile", 1, 60.0),
        _line("Kopfzeile", 2, 60.1 + FURNITURE_Y_TOLERANCE),
    ]
    assert remove_furniture(inside)[1] == 1
    assert remove_furniture(outside)[1] == 0


def test_short_tokens_never_count() -> None:
    # Tick glyphs and section numbers recur at similar heights on every page.
    lines = [
        _line("X", 1, 484.0),
        _line("X", 2, 484.0),
        _line("6", 1, 462.8),
        _line("8", 2, 462.8),
        _line("ab", 1, 300.0),
        _line("ab", 2, 300.0),
    ]
    assert remove_furniture(lines) == (lines, 0)


def test_needs_most_pages() -> None:
    # Five pages: a line on two of them is not furniture, on three it is.
    two = [_line("Hinweis zum Formular", p, 700.0) for p in (1, 2)]
    three = [_line("Hinweis zum Formular", p, 700.0) for p in (1, 2, 3)]
    words = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon")
    filler = [_line(word, p, 100.0) for p, word in enumerate(words, start=1)]
    assert remove_furniture(filler + two)[1] == 0
    assert remove_furniture(filler + three)[1] == 2
