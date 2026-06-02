from __future__ import annotations

from uuid import uuid4

from shared.services.ingestion.lv.backrefs import resolve_backrefs
from shared.services.ingestion.lv.linking import link_positions
from shared.services.ingestion.lv.types import SlicedPosition


def _pos(
    oz: str,
    *,
    is_title: bool = False,
    langtext: str = "body",
    linked_oz: str | None = None,
) -> SlicedPosition:
    return SlicedPosition(
        oz=oz,
        is_title=is_title,
        kurztext=f"kurz {oz}",
        langtext=langtext,
        hinweis=None,
        menge="1,00",
        einheit="m",
        stl_nr=None,
        linked_oz=linked_oz,
        positionstyp=None,
        pages=[1],
        source_line_uuids=[uuid4()],
    )


def test_level_parent_and_prev_next_chain() -> None:
    positions = [
        _pos("1", is_title=True),
        _pos("1.1"),
        _pos("1.3", is_title=True),
        _pos("1.3.7"),
        _pos("2", is_title=True),
    ]

    links = link_positions(positions)

    assert links["1"].level == 1 and links["1"].parent_oz is None
    assert links["1.1"].level == 2 and links["1.1"].parent_oz == "1"
    assert links["1.3.7"].level == 3 and links["1.3.7"].parent_oz == "1.3"
    # Titles are excluded from the prev/next chain; only priced positions chain.
    assert links["1.1"].next_oz == "1.3.7"
    assert links["1.3.7"].prev_oz == "1.1"
    assert links["1"].prev_oz is None and links["1"].next_oz is None


def test_parent_skips_absent_intermediate_level() -> None:
    # 1.3 has no row, so the parent of 1.3.7 falls back to 1.
    links = link_positions([_pos("1", is_title=True), _pos("1.3.7")])
    assert links["1.3.7"].parent_oz == "1"


def test_backref_composes_resolved_from_predecessor_and_delta() -> None:
    positions = [
        _pos("1.1", langtext="Oberboden abtragen."),
        _pos("1.2", langtext="wie in voriger Position beschrieben jedoch Tiefe ueber 1 m.", linked_oz="1.1"),
        _pos("1.3", langtext="wie in voriger Position jedoch Tiefe ueber 2 m.", linked_oz="1.2"),
    ]

    resolved = resolve_backrefs(positions)

    assert resolved["1.1"] is None
    assert resolved["1.2"] == "Oberboden abtragen. jedoch Tiefe ueber 1 m."
    # The chain resolves recursively: 1.3 inherits 1.2's already-resolved body.
    assert resolved["1.3"] == "Oberboden abtragen. jedoch Tiefe ueber 1 m. jedoch Tiefe ueber 2 m."


def test_backref_falls_back_to_previous_when_linked_oz_absent() -> None:
    positions = [
        _pos("1.1", langtext="Base body."),
        _pos("1.2", langtext="wie in voriger Position jedoch anders."),
    ]
    resolved = resolve_backrefs(positions)
    assert resolved["1.2"] == "Base body. jedoch anders."
