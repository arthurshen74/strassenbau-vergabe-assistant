from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from shared.models.llm_output_schemas import LVExtraction, LVPosition
from shared.models.source_line import SourceLine
from shared.services.ingestion.lv import postprocess
from shared.services.ingestion.lv.validate import LVValidationError


def _line(line_id: int, page: int, text: str) -> SourceLine:
    return SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=uuid4(),
        line_id=line_id,
        page=page,
        bbox=(0, 0, 1, 1),
        line_text=text,
    )


def _pos(
    oz: str,
    kurztext_line: int,
    *,
    is_title: bool = False,
    langtext: tuple[int, int] | None = None,
    hinweis: tuple[int, int] | None = None,
    stl_nr: str | None = None,
    menge: str | None = None,
    einheit: str | None = None,
    linked_oz: str | None = None,
    positionstyp: str | None = None,
) -> LVPosition:
    return LVPosition(
        oz=oz,
        is_title=is_title,
        kurztext_line=kurztext_line,
        langtext_start=langtext[0] if langtext else -1,
        langtext_end=langtext[1] if langtext else -1,
        hinweis_start=hinweis[0] if hinweis else -1,
        hinweis_end=hinweis[1] if hinweis else -1,
        stl_nr=stl_nr,
        menge=menge,
        einheit=einheit,
        linked_oz=linked_oz,
        positionstyp=positionstyp,
    )


def _sample() -> tuple[LVExtraction, list[SourceLine]]:
    src = [
        _line(0, 1, "1 Strassenbau"),
        _line(1, 1, "1.1 StL-Nr.: 21 109"),
        _line(2, 1, "Oberboden abtragen und"),
        _line(3, 1, "seitlich lagern."),
        _line(4, 2, "Hinweis: nur bei trockener Witterung."),
    ]
    extraction = LVExtraction(
        positions=[
            _pos("1", 0, is_title=True),
            _pos(
                "1.1",
                1,
                langtext=(2, 3),
                hinweis=(4, 4),
                stl_nr="21 109",
                menge="25,00",
                einheit="m",
            ),
        ]
    )
    return extraction, src


def test_slices_verbatim_text_pages_and_titles() -> None:
    extraction, src = _sample()

    result = postprocess.run(extraction, src)

    titel, item = result.items
    assert titel.oz == "1" and titel.positionstyp == "Titel"
    assert titel.menge == Decimal(0) and titel.langtext == "1 Strassenbau"

    assert item.kurztext == "1.1 StL-Nr.: 21 109"
    assert item.langtext == "Oberboden abtragen und\nseitlich lagern."  # joined verbatim
    assert item.menge == Decimal("25.00") and item.einheit == "m"
    assert item.hinweis == "Hinweis: nur bei trockener Witterung."
    assert item.pages == [1, 2]  # kurztext+langtext on p1, hinweis on p2
    assert item.stl_nr == "21 109"
    assert result.warnings == []


def test_source_line_uuids_track_covered_lines() -> None:
    extraction, src = _sample()
    result = postprocess.run(extraction, src)
    item = result.items[1]
    # kurztext(1) + langtext(2,3) + hinweis(4)
    assert item.source_line_uuids == [src[1].source_line_uuid, src[2].source_line_uuid, src[3].source_line_uuid, src[4].source_line_uuid]


def test_out_of_range_span_is_hard_failure() -> None:
    src = [_line(0, 1, "1.1 x")]
    extraction = LVExtraction(positions=[_pos("1.1", 0, langtext=(5, 6), menge="1,00", einheit="m")])
    with pytest.raises(LVValidationError):
        postprocess.run(extraction, src)


def test_overlapping_bodies_are_hard_failure() -> None:
    src = [_line(i, 1, f"line {i}") for i in range(4)]
    extraction = LVExtraction(
        positions=[
            _pos("1.1", 0, langtext=(1, 2), menge="1,00", einheit="m"),
            _pos("1.2", 2, langtext=(3, 3), menge="1,00", einheit="m"),  # claims line 2 again
        ]
    )
    with pytest.raises(LVValidationError):
        postprocess.run(extraction, src)


def test_non_monotonic_oz_is_hard_failure() -> None:
    src = [_line(0, 1, "2 a"), _line(1, 1, "1 b")]
    extraction = LVExtraction(positions=[_pos("2", 0, is_title=True), _pos("1", 1, is_title=True)])
    with pytest.raises(LVValidationError):
        postprocess.run(extraction, src)


def test_unparseable_menge_is_hard_failure() -> None:
    src = [_line(0, 1, "1.1 x"), _line(1, 1, "body")]
    extraction = LVExtraction(positions=[_pos("1.1", 0, langtext=(1, 1), menge="zwei", einheit="m")])
    with pytest.raises(LVValidationError):
        postprocess.run(extraction, src)


def test_missing_langtext_and_menge_are_soft_warnings() -> None:
    src = [_line(0, 1, "1.1 only a header line")]
    extraction = LVExtraction(positions=[_pos("1.1", 0)])  # priced position, no langtext/menge

    result = postprocess.run(extraction, src)

    assert any("no langtext" in w for w in result.warnings)
    assert any("no menge" in w for w in result.warnings)
    # falls back so langtext is non-empty for persistence
    assert result.items[0].langtext == "1.1 only a header line"
