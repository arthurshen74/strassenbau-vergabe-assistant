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


def test_duplicate_oz_is_coalesced_not_fatal() -> None:
    # The LLM split one position into two entries sharing line 2; coalescing unions their lines
    # (the shared line appears once), takes the highest menge and the last einheit. Without it,
    # the overlap check fails (the production failure: "line_id N claimed by both X and X").
    src = [
        _line(0, 1, "1.5.30 header"),
        _line(1, 1, "Verify"),
        _line(2, 1, "the Frostschutzschicht with a"),
        _line(3, 1, "water drainage test"),
    ]
    extraction = LVExtraction(
        positions=[
            _pos("1.5.30", 0, langtext=(1, 2), menge="25,00", einheit="m"),
            _pos("1.5.30", 0, langtext=(2, 3), menge="2.400,00", einheit="m2"),
        ]
    )

    result = postprocess.run(extraction, src)

    assert [item.oz for item in result.items] == ["1.5.30"]  # collapsed to one
    item = result.items[0]
    assert item.kurztext == "1.5.30 header"
    # union of lines {1,2,3}; the shared line 2 appears exactly once
    assert item.langtext == "Verify\nthe Frostschutzschicht with a\nwater drainage test"
    assert item.menge == Decimal("2400")  # highest wins
    assert item.einheit == "m2"  # last wins
    assert any("coalesced 2 entries for OZ 1.5.30" in w for w in result.warnings)


def test_triplicate_oz_coalesces_all_fragments() -> None:
    src = [_line(i, 1, f"frag {i}") for i in range(5)]
    extraction = LVExtraction(
        positions=[
            _pos("2.1", 0, langtext=(1, 1), menge="1,00", einheit="m"),
            _pos("2.1", 0, langtext=(2, 2), menge="3,00", einheit="St"),
            _pos("2.1", 0, langtext=(3, 4), menge="2,00", einheit=None),
        ]
    )

    result = postprocess.run(extraction, src)

    item = result.items[0]
    assert item.langtext == "frag 1\nfrag 2\nfrag 3\nfrag 4"  # union of all three fragments
    assert item.menge == Decimal("3")  # highest across the three
    assert item.einheit == "St"  # last non-empty (third entry's einheit is None)


def test_kurztext_line_inside_langtext_span_is_not_self_overlap() -> None:
    # The finer pdftotext lines make the LLM start the langtext span at the kurztext line
    # (the production failure: "line_id 654 claimed by both 1.5.30 and 1.5.30"). That must not
    # trip the overlap check, and the header line must not be duplicated into langtext.
    src = [
        _line(0, 1, "1.5.30 header"),
        _line(1, 1, "body line one"),
        _line(2, 1, "body line two"),
    ]
    extraction = LVExtraction(
        positions=[_pos("1.5.30", 0, langtext=(0, 2), menge="1,00", einheit="m")]
    )

    result = postprocess.run(extraction, src)

    item = result.items[0]
    assert item.kurztext == "1.5.30 header"
    assert item.langtext == "body line one\nbody line two"  # header excluded, not duplicated


def test_out_of_range_span_is_hard_failure() -> None:
    src = [_line(0, 1, "1.1 x")]
    extraction = LVExtraction(positions=[_pos("1.1", 0, langtext=(5, 6), menge="1,00", einheit="m")])
    with pytest.raises(LVValidationError):
        postprocess.run(extraction, src)


def test_next_position_header_in_langtext_is_resolved() -> None:
    # The finer pdftotext lines make one position's langtext span overshoot into the next
    # position's header (the production failure: "line_id N claimed by both X and Y" for
    # consecutive OZs). The header is a hard boundary, so the overshoot is trimmed -- the
    # contested line stays with the position whose header it is.
    src = [_line(i, 1, f"line {i}") for i in range(4)]
    extraction = LVExtraction(
        positions=[
            _pos("1.1", 0, langtext=(1, 2), menge="1,00", einheit="m"),  # overshoots into 1.2
            _pos("1.2", 2, langtext=(3, 3), menge="1,00", einheit="m"),
        ]
    )

    result = postprocess.run(extraction, src)

    first, second = result.items
    assert first.langtext == "line 1"  # line 2 (1.2's header) trimmed off
    assert second.kurztext == "line 2" and second.langtext == "line 3"
    assert any("dropped langtext line 2 (header of 1.2)" in w for w in result.warnings)


def test_overlapping_langtext_keeps_earliest_position() -> None:
    # Neither position owns the contested line as a header: the earlier OZ in document order
    # keeps it, the later one drops it.
    src = [_line(i, 1, f"line {i}") for i in range(5)]
    extraction = LVExtraction(
        positions=[
            _pos("1.1", 0, langtext=(1, 2), menge="1,00", einheit="m"),
            _pos("1.2", 3, langtext=(2, 4), menge="1,00", einheit="m"),  # langtext reaches back to 2
        ]
    )

    result = postprocess.run(extraction, src)

    first, second = result.items
    assert first.langtext == "line 1\nline 2"  # 1.1 keeps the shared line
    assert second.langtext == "line 4"  # 1.2 drops line 2, keeps line 4 (3 is its own header)
    assert any("dropped langtext line 2 (already claimed by 1.1)" in w for w in result.warnings)


def test_shared_kurztext_line_is_hard_failure() -> None:
    # Two distinct OZs claiming the same header line is an irreconcilable conflict; the overlap
    # check still fails loudly rather than guessing which position owns the line.
    src = [_line(i, 1, f"line {i}") for i in range(3)]
    extraction = LVExtraction(
        positions=[
            _pos("1.1", 0, langtext=(1, 1), menge="1,00", einheit="m"),
            _pos("1.2", 0, langtext=(2, 2), menge="1,00", einheit="m"),  # same kurztext line
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
