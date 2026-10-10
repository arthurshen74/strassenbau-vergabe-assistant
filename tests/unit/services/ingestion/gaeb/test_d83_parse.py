"""Unit tests for the GAEB 90 D83 parser.

Fixtures build 80-column records mirroring real D83 exports (Zeilenart in columns 1-2,
Satznummer in 75-80). The deep-hierarchy test uses the standard '1122PPPPI' OZ mask; the
focused tests use a flat '11PPPP' mask so OZs stay readable.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from shared.services.ingestion.gaeb import (
    D83ParseError,
    GaebParseError,
    is_d83_file,
    parse_d83,
)
from shared.services.ingestion.lv.types import (
    AddTextBlock,
    LVParseResult,
    LVTextPlacement,
    ResolvedItem,
)

MASK_STANDARD = "1122PPPPI"
MASK_FLAT = "11PPPP"
ENCODING = "cp850"


def _record(body: str) -> str:
    return body.ljust(74) + "000000"


def _eroeffnung(mask: str) -> str:
    return _record(f"00{'':8}83L".ljust(62) + f"{mask}90")


def _gruppe(oz: str) -> str:
    return _record(f"11{oz:<9}N")


def _gruppe_name(text: str) -> str:
    return _record(f"12{text}")


def _position(
    oz: str,
    *,
    menge: str = "00000001000",
    einheit: str = "m",
    posart: str = "NN",
    stl: str = "",
) -> str:
    body = f"21{oz:<9}{posart:<2}N".ljust(23) + menge + f"{einheit:<4}"
    return _record(body.ljust(43) + stl)


def _kurztext(text: str) -> str:
    return _record(f"25{text}")


def _langtext(text: str) -> str:
    return _record(f"26   {text}")


def _hinweis_begin(oz: str = "") -> str:
    return _record(f"20{oz:<9}")


def _gruppe_end() -> str:
    return _record("31")


def _abschluss() -> str:
    return _record("99")


def _parse(lines: list[str]) -> LVParseResult:
    return parse_d83("\n".join(lines).encode(ENCODING))


def _by_oz(result: LVParseResult) -> dict[str, ResolvedItem]:
    return {item.oz: item for item in result.items}


def test_emits_titles_and_positions_with_links() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_STANDARD),
                _gruppe("01"),
                _gruppe_name("Straßenbau"),
                _gruppe("0101"),
                _gruppe_name("Erdarbeiten"),
                _position(
                    "01010001", menge="00000002500", einheit="m3", stl="21910110711"
                ),
                _kurztext("Oberboden abtragen"),
                _kurztext("und seitlich lagern"),
                _langtext("Oberboden abtragen und"),
                _langtext("seitlich lagern."),
                _position("01010002", menge="00000001000", einheit="m3"),
                _kurztext("Boden liefern"),
                _langtext("Boden liefern und einbauen."),
                _gruppe_end(),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert list(items) == ["01", "01.01", "01.01.0001", "01.01.0002"]

    titel = items["01"]
    assert titel.positionstyp == "Titel"
    assert titel.kurztext == "Straßenbau"
    assert titel.langtext == "Straßenbau"
    assert titel.menge == Decimal(0)
    assert titel.level == 1
    assert titel.parent_oz is None

    position = items["01.01.0001"]
    assert position.kurztext == "Oberboden abtragen und seitlich lagern"
    assert position.langtext == "Oberboden abtragen und\nseitlich lagern."
    assert position.menge == Decimal("2.500")
    assert position.einheit == "m3"
    assert position.stl_nr == "21910110711"
    assert position.positionstyp == "Normalposition"
    assert position.level == 3
    assert position.parent_oz == "01.01"
    assert position.prev_oz is None
    assert position.next_oz == "01.01.0002"
    assert position.pages == []
    assert position.source_line_uuids == []

    assert items["01.01.0002"].prev_oz == "01.01.0001"


def test_hinweis_governs_following_positions_until_gruppe_ends() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Vor dem Hinweis"),
                _hinweis_begin(),
                _langtext("Fugen nach ZTV Fug-StB 15"),
                _langtext("herstellen."),
                _position("010002"),
                _kurztext("Nach dem Hinweis"),
                _gruppe_end(),
                _gruppe("02"),
                _gruppe_name("Anderes Gewerk"),
                _position("020001"),
                _kurztext("Anderer Abschnitt"),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert items["01.0001"].hinweis is None
    assert items["01.0002"].hinweis == "Fugen nach ZTV Fug-StB 15\nherstellen."
    assert items["02"].hinweis is None  # titles carry no Hinweis
    assert items["02.0001"].hinweis is None  # scope ended with the LV-Gruppe


def test_vertragliche_regelungen_are_vortext_not_position_hinweis() -> None:
    result = _parse(
        [
            _record("T0"),
            _record("T1Vorbemerkungen"),
            _record("T1"),
            _record("T1Für diese Ausschreibung gilt die VOB/B."),
            _record("T1Zweite Zeile."),
            _record("T9"),
            _eroeffnung(MASK_FLAT),
            _gruppe("01"),
            _gruppe_name("Bau"),
            _position("010001"),
            _kurztext("Eins"),
            _gruppe_end(),
            _abschluss(),
        ]
    )
    # One block, lines kept, the blank T1 a paragraph break; no heading in GAEB 90.
    assert result.vortext() == [
        AddTextBlock(
            placement=LVTextPlacement.BEFORE_BOQ,
            heading=None,
            body=(
                "Vorbemerkungen\n\nFür diese Ausschreibung gilt die VOB/B.\n"
                "Zweite Zeile."
            ),
            order=0,
        )
    ]
    assert result.nachtext() == []
    assert result.remarks == []
    assert _by_oz(result)["01.0001"].hinweis is None
    assert result.warnings == []


def test_t_lines_after_abschluss_are_nachtext_with_warning() -> None:
    result = _parse(
        [
            _eroeffnung(MASK_FLAT),
            _gruppe("01"),
            _gruppe_name("Bau"),
            _position("010001"),
            _kurztext("Eins"),
            _gruppe_end(),
            _abschluss(),
            _record("T0"),
            _record("T1Bietererklärung: Bindefrist 60 Tage."),
            _record("T9"),
        ]
    )
    assert result.vortext() == []
    assert result.nachtext() == [
        AddTextBlock(
            placement=LVTextPlacement.AFTER_BOQ,
            heading=None,
            body="Bietererklärung: Bindefrist 60 Tage.",
            order=0,
        )
    ]
    assert any("Nachtext" in warning for warning in result.warnings)


def test_leading_root_hinweis_governs_every_following_position() -> None:
    result = _parse(
        [
            _eroeffnung(MASK_FLAT),
            _hinweis_begin(),
            _langtext("Gilt für das gesamte LV."),
            _gruppe("00"),
            _gruppe_name("Verkehrssicherung"),
            _position("000001"),
            _kurztext("In Abschnitt 00"),
            _gruppe_end(),
            _gruppe("01"),
            _gruppe_name("Anderes Gewerk"),
            _position("010001"),
            _kurztext("In Abschnitt 01"),
            _gruppe_end(),
            _abschluss(),
        ]
    )
    items = _by_oz(result)
    # Scope is positional: the innermost open container is the LV itself.
    assert items["00.0001"].hinweis == "Gilt für das gesamte LV."
    assert items["01.0001"].hinweis == "Gilt für das gesamte LV."
    assert items["00"].hinweis is None
    assert result.leading_root_remarks() == result.remarks
    assert result.remarks[0].parent_oz is None
    assert result.remarks[0].index == 0
    assert result.vortext() == []  # a Remark is never promoted to a Zusatztext


def test_hinweis_nodes_record_parent_index_heading_and_oz() -> None:
    result = _parse(
        [
            _eroeffnung(MASK_STANDARD),
            _gruppe("01"),
            _gruppe_name("Straßenbau"),
            _gruppe("0101"),
            _gruppe_name("Erdarbeiten"),
            _hinweis_begin("01010000"),
            _kurztext("Hinweis zu Titel 01.01"),
            _langtext("Aushub ist zu lagern."),
            _position("01010001"),
            _kurztext("Eins"),
            _hinweis_begin(),
            _langtext("Zwischen zwei Positionen."),
            _position("01010002"),
            _kurztext("Zwei"),
            _gruppe_end(),
            _hinweis_begin(),
            _langtext("Nach Titel 01.01, vor Titel 01.02."),
            _gruppe("0102"),
            _gruppe_name("Entwässerung"),
            _position("01020001"),
            _kurztext("Drei"),
            _gruppe_end(),
            _gruppe_end(),
            _hinweis_begin(),
            _langtext("Zusammenstellung"),
            _abschluss(),
        ]
    )
    assert result.warnings == []
    titel, mid, between, trailing = result.remarks

    assert titel.oz == "01.01.0000"
    assert titel.heading == "Hinweis zu Titel 01.01"
    assert titel.body == "Aushub ist zu lagern."
    assert (titel.parent_oz, titel.index) == ("01.01", 0)
    assert (mid.oz, mid.heading, mid.parent_oz, mid.index) == (None, None, "01.01", 2)
    assert (between.parent_oz, between.index) == ("01", 1)
    assert (trailing.parent_oz, trailing.index) == (None, 1)
    assert result.leading_root_remarks() == []

    items = _by_oz(result)
    assert items["01.01.0001"].hinweis == (
        "Hinweis zu Titel 01.01\nAushub ist zu lagern."
    )
    assert items["01.01.0002"].hinweis == (
        "Hinweis zu Titel 01.01\nAushub ist zu lagern.\n\nZwischen zwei Positionen."
    )
    # The parent-level Hinweis reaches the next Titel's positions; the sibling Titel's
    # Hinweise do not.
    assert items["01.02.0001"].hinweis == "Nach Titel 01.01, vor Titel 01.02."


def test_position_directly_under_titel_with_blank_segment_parses() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_STANDARD),
                _gruppe("01"),
                _gruppe_name("Titel"),
                _position("01     1"),
                _kurztext("Direkt unter dem Titel"),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert list(items) == ["01", "01.0001"]
    assert items["01.0001"].parent_oz == "01"
    assert items["01.0001"].level == 2


def test_backref_wie_in_voriger_position_composes_delta() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Suchgraben herstellen"),
                _langtext("Suchgraben herstellen, Tiefe bis 1,25 m."),
                _position("010002"),
                _kurztext("Leistung wie vor. Pos.; T 1,75"),
                _langtext("Leistung ausführen, wie in voriger Position beschrieben"),
                _langtext("jedoch Tiefe über 1,25 m bis 1,75 m."),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    linked = items["01.0002"]
    assert linked.linked_oz == "01.0001"
    assert linked.langtext_resolved == (
        "Suchgraben herstellen, Tiefe bis 1,25 m. jedoch Tiefe über 1,25 m bis 1,75 m."
    )
    assert items["01.0001"].langtext_resolved is None


def test_backref_desgl_links_previous_priced_position() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Bordstein setzen"),
                _langtext("Bordstein auf Betonfundament setzen."),
                _position("010002"),
                _kurztext("desgl. Radius 5 m"),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert items["01.0002"].linked_oz == "01.0001"
    assert items["01.0002"].langtext_resolved is not None


def test_backref_explicit_oz_reference_ignores_zero_padding() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Rohr verlegen DN 150"),
                _langtext("Rohr DN 150 verlegen."),
                _position("010002"),
                _kurztext("Zwischenposition"),
                _langtext("Etwas anderes."),
                _position("010003"),
                _kurztext("Rohr verlegen DN 200"),
                _langtext("Ausführung wie Pos. 1.1, jedoch DN 200."),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert items["01.0003"].linked_oz == "01.0001"


def test_posart_maps_to_positionstyp() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001", posart="NN"),
                _kurztext("Normal"),
                _position("010002", posart="GN"),
                _kurztext("Grund"),
                _position("010003", posart="AN"),
                _kurztext("Alternativ"),
                _position("010004", posart="NE"),
                _kurztext("Bedarf"),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert items["01.0001"].positionstyp == "Normalposition"
    assert items["01.0002"].positionstyp == "Grundposition"
    assert items["01.0003"].positionstyp == "Alternativposition"
    assert items["01.0004"].positionstyp == "Bedarfsposition"


def test_textergaenzung_prefix_is_blanked_in_langtext() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Baubüro aufbauen"),
                _record("2611ABaubüro für den AG antransportieren"),
                _record("2611Aund nach Unterlagen des AG aufbauen."),
                _langtext("Anschließend räumen."),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    assert items["01.0001"].langtext == (
        "Baubüro für den AG antransportieren\n"
        "und nach Unterlagen des AG aufbauen.\n"
        "Anschließend räumen."
    )


def test_freitext_placeholder_is_blanked_in_kurztext_and_langtext() -> None:
    items = _by_oz(
        _parse(
            [
                _eroeffnung(MASK_FLAT),
                _gruppe("01"),
                _gruppe_name("Bau"),
                _position("010001"),
                _kurztext("Arbeitsstelle*... Freitext ..."),
                _langtext("Breite ... Freitext ... m herstellen."),
                _gruppe_end(),
                _abschluss(),
            ]
        )
    )
    position = items["01.0001"]
    assert position.kurztext == "Arbeitsstelle*"
    assert "Freitext" not in position.langtext
    assert position.langtext == f"Breite {' ' * 16} m herstellen."


def test_blank_menge_reads_as_zero_with_warning() -> None:
    result = _parse(
        [
            _eroeffnung(MASK_FLAT),
            _gruppe("01"),
            _gruppe_name("Bau"),
            _position("010001", menge=" " * 11),
            _kurztext("Ohne Menge"),
            _gruppe_end(),
            _abschluss(),
        ]
    )
    assert result.items[-1].menge == Decimal(0)
    assert any("blank Menge" in warning for warning in result.warnings)


def test_cp850_umlauts_decode() -> None:
    result = _parse(
        [
            _eroeffnung(MASK_FLAT),
            _gruppe("01"),
            _gruppe_name("Straßenbau"),
            _position("010001"),
            _kurztext("Entwässerungsleitung prüfen"),
            _gruppe_end(),
            _abschluss(),
        ]
    )
    assert result.items[0].kurztext == "Straßenbau"
    assert result.items[1].kurztext == "Entwässerungsleitung prüfen"


def test_duplicate_oz_raises() -> None:
    lines = [
        _eroeffnung(MASK_FLAT),
        _gruppe("01"),
        _gruppe_name("Bau"),
        _position("010001"),
        _kurztext("Eins"),
        _position("010001"),
        _kurztext("Nochmal"),
        _gruppe_end(),
        _abschluss(),
    ]
    with pytest.raises(GaebParseError, match="duplicate OZ"):
        _parse(lines)


def test_unclosed_gruppe_raises() -> None:
    lines = [
        _eroeffnung(MASK_FLAT),
        _gruppe("01"),
        _gruppe_name("Bau"),
        _position("010001"),
        _kurztext("Eins"),
        _abschluss(),
    ]
    with pytest.raises(D83ParseError, match="unclosed"):
        _parse(lines)


def test_position_before_eroeffnung_raises() -> None:
    with pytest.raises(D83ParseError, match="Eroeffnungssatz"):
        _parse([_gruppe("01")])


def test_is_d83_file() -> None:
    assert is_d83_file("P22039_LV1.D83")
    assert is_d83_file("projekt_lv.d83")
    assert not is_d83_file("Projekt_LV1.pdf")
    assert not is_d83_file("projekt.x83")


# Real exports live in the untracked eval/context tree; exercise them when present.
_EVAL_CONTEXT = Path(__file__).parents[5] / "eval" / "context"
_REAL_FILES = {
    "P0372026/P0372026_LV.d83": (93, 82),
    "P22039/P22039_LV1.D83": (161, 144),
    "PS231202600001/PS231202600001_LV.D83": (123, 101),
}


@pytest.mark.parametrize("relative_path", sorted(_REAL_FILES))
def test_real_d83_exports_parse_clean(relative_path: str) -> None:
    path = _EVAL_CONTEXT / relative_path
    if not path.exists():
        pytest.skip(f"{relative_path} not present")
    result = parse_d83(path.read_bytes())
    total, priced = _REAL_FILES[relative_path]
    assert len(result.items) == total
    assert sum(1 for item in result.items if item.positionstyp != "Titel") == priced
    assert result.warnings == []
