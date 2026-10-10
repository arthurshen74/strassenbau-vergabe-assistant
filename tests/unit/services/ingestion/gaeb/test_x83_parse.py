"""Unit tests for the GAEB DA XML X83 parser.

The synthetic fixture mirrors the shape of real exports: pretty-printed XML where text
lives in `span` elements, lines break via `br`, and inter-element whitespace is noise.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from shared.services.ingestion.gaeb import X83ParseError, is_x83_file, parse_x83
from shared.services.ingestion.lv.types import (
    AddTextBlock,
    LVParseResult,
    LVTextPlacement,
    ResolvedItem,
)

NS = "http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"


def _boq_info() -> str:
    return """
  <BoQInfo>
   <BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
   <BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
   <BoQBkdn><Type>Item</Type><Length>4</Length></BoQBkdn>
  </BoQInfo>"""


def _item(
    rno: str,
    *,
    qty: str = "1.000",
    qu: str = "m",
    outline: str = "Kurztext",
    detail: str = "<p><span>Langtext.</span></p>",
    extra: str = "",
    stl: str = "",
) -> str:
    stl_el = f"<StLNo>{stl}</StLNo>" if stl else ""
    return f"""
      <Item RNoPart="{rno}">
       <Qty>{qty}</Qty>
       <QU>{qu}</QU>
       {extra}
       <Description>
        {stl_el}
        <CompleteText>
         <DetailTxt><Text>{detail}</Text></DetailTxt>
         <OutlineText><OutlTxt><TextOutlTxt><p><span>{outline}</span></p></TextOutlTxt></OutlTxt></OutlineText>
        </CompleteText>
       </Description>
      </Item>"""


def _remark(detail: str, *, outline: str | None = None, rno: str | None = None) -> str:
    outline_el = (
        f"<OutlineText><OutlTxt><TextOutlTxt><p><span>{outline}</span></p>"
        "</TextOutlTxt></OutlTxt></OutlineText>"
        if outline
        else ""
    )
    rno_attr = f' RNoPart="{rno}"' if rno else ""
    return f"""
      <Remark{rno_attr}>
       <Description>
        <CompleteText>
         <DetailTxt><Text>{detail}</Text></DetailTxt>
         {outline_el}
        </CompleteText>
       </Description>
      </Remark>"""


def _add_text(detail: str, *, outline: str | None = None) -> str:
    heading = f"<OutlineAddText>{outline}</OutlineAddText>" if outline else ""
    return f"<AddText>{heading}<DetailAddText>{detail}</DetailAddText></AddText>"


def _document(
    body: str, *, info: str | None = None, before: str = "", after: str = ""
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<GAEB xmlns="{NS}">
 <Award>
  <DP>83</DP>
  {before}
  <BoQ>{info if info is not None else _boq_info()}
   <BoQBody>{body}</BoQBody>
  </BoQ>
  {after}
 </Award>
</GAEB>""".encode()


def _by_oz(result: LVParseResult) -> dict[str, ResolvedItem]:
    return {item.oz: item for item in result.items}


def test_categories_and_items_with_padded_oz_and_links() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Erdbau</span></p></LblTx>
     <BoQBody>
      <BoQCtgy RNoPart="2">
       <LblTx><p><span>Oberboden</span></p></LblTx>
       <BoQBody>
        <Itemlist>
         {
            _item(
                "10",
                qty="2.500",
                qu="m3",
                outline="Oberboden abtragen",
                stl="1910110711",
                detail="<p><span>Oberboden abtragen und</span><br/><span>seitlich lagern.</span></p>",
            )
        }
         {_item("20", outline="Boden liefern")}
        </Itemlist>
       </BoQBody>
      </BoQCtgy>
     </BoQBody>
    </BoQCtgy>"""
    )
    result = parse_x83(data)
    assert result.warnings == []
    items = _by_oz(result)
    assert list(items) == ["01", "01.02", "01.02.0010", "01.02.0020"]

    titel = items["01"]
    assert titel.positionstyp == "Titel"
    assert titel.kurztext == "Erdbau"
    assert titel.menge == Decimal(0)
    assert titel.level == 1

    position = items["01.02.0010"]
    assert position.kurztext == "Oberboden abtragen"
    assert position.langtext == "Oberboden abtragen und\nseitlich lagern."
    assert position.menge == Decimal("2.500")
    assert position.einheit == "m3"
    assert position.stl_nr == "1910110711"
    assert position.positionstyp == "Normalposition"
    assert position.level == 3
    assert position.parent_oz == "01.02"
    assert position.next_oz == "01.02.0020"
    assert position.pages == []
    assert position.source_line_uuids == []


def test_remark_governs_following_positions_until_category_ends() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", outline="Vor dem Hinweis")}
       {_remark("<p><span>Vorbemerkung zu nachfolgender Position:</span><br/><span>Gilt ab hier.</span></p>")}
       {_item("20", outline="Nach dem Hinweis")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>
    <BoQCtgy RNoPart="2">
     <LblTx><p><span>Anderes Gewerk</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", outline="Anderer Abschnitt")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    items = _by_oz(parse_x83(data))
    assert items["01.0010"].hinweis is None
    assert (
        items["01.0020"].hinweis
        == "Vorbemerkung zu nachfolgender Position:\nGilt ab hier."
    )
    assert items["02.0010"].hinweis is None  # scope ended with the category


def test_add_texts_before_and_after_boq_are_vortext_and_nachtext() -> None:
    body = f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    data = _document(
        body,
        before=_add_text(
            "<p><span>Baubeschreibung</span></p><p/><p><span>1. Allgemeines</span></p>",
            outline='<p style="text-align:left;"><span>Baubeschreibung</span></p>',
        )
        + _add_text("<p><span>Zweiter Vortext.</span></p>"),
        after=_add_text(
            "<p><span>Bindefrist 60 Tage.</span></p>",
            outline="<span>Bietererklärung</span>",
        ),
    )
    result = parse_x83(data)
    assert result.warnings == []
    # Document order relative to the BoQ is the only Vortext/Nachtext signal; the
    # heading survives its markup; an empty `p` is a paragraph break.
    assert result.vortext() == [
        AddTextBlock(
            placement=LVTextPlacement.BEFORE_BOQ,
            heading="Baubeschreibung",
            body="Baubeschreibung\n\n1. Allgemeines",
            order=0,
        ),
        AddTextBlock(
            placement=LVTextPlacement.BEFORE_BOQ,
            heading=None,
            body="Zweiter Vortext.",
            order=1,
        ),
    ]
    assert result.nachtext() == [
        AddTextBlock(
            placement=LVTextPlacement.AFTER_BOQ,
            heading="Bietererklärung",
            body="Bindefrist 60 Tage.",
            order=0,
        )
    ]
    assert result.remarks == []
    assert _by_oz(result)["01.0010"].hinweis is None


def test_remark_heading_joins_body_unless_body_repeats_it() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {
            _remark(
                "<p><span>Abrechnung nach Grundflächen.</span></p>",
                outline="Hinweis zu Bewuchs",
            )
        }
       {
            _remark(
                "<p><span>Hinweis zu nachfolgender OZ:</span><br/>"
                "<span>Bauzaun.</span></p>",
                outline="Hinweis zu nachfolgender OZ:",
            )
        }
       {_remark("<p/>", outline="Bypass bei EÜ-Ringbahnzufahrt")}
       {_item("10")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    result = parse_x83(data)
    assert [(r.heading, r.body) for r in result.remarks] == [
        ("Hinweis zu Bewuchs", "Abrechnung nach Grundflächen."),
        ("Hinweis zu nachfolgender OZ:", "Hinweis zu nachfolgender OZ:\nBauzaun."),
        ("Bypass bei EÜ-Ringbahnzufahrt", ""),
    ]
    assert _by_oz(result)["01.0010"].hinweis == (
        "Hinweis zu Bewuchs\nAbrechnung nach Grundflächen."
        "\n\n"
        "Hinweis zu nachfolgender OZ:\nBauzaun."
        "\n\n"
        "Bypass bei EÜ-Ringbahnzufahrt"
    )


def test_remark_nodes_record_parent_index_and_rno_part() -> None:
    data = _document(
        f"""
    {_remark("<p><span>Gilt für das gesamte LV.</span></p>", rno="1")}
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      {_remark("<p><span>Gilt für Titel 01.</span></p>")}
      <Itemlist>
       {_item("10")}
       {_remark("<p><span>Gilt ab hier.</span></p>")}
       {_item("20")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>
    <BoQCtgy RNoPart="2">
     <LblTx><p><span>Anderes Gewerk</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    result = parse_x83(data)
    root, titel, mid = result.remarks
    assert (root.oz, root.parent_oz, root.index) == ("0001", None, 0)
    assert (titel.oz, titel.parent_oz, titel.index) == (None, "01", 0)
    assert (mid.parent_oz, mid.index) == ("01", 2)
    assert result.leading_root_remarks() == [root]

    items = _by_oz(result)
    assert items["01.0010"].hinweis == "Gilt für das gesamte LV.\n\nGilt für Titel 01."
    assert items["01.0020"].hinweis == (
        "Gilt für das gesamte LV.\n\nGilt für Titel 01.\n\nGilt ab hier."
    )
    assert items["02.0010"].hinweis == "Gilt für das gesamte LV."


def test_perf_descr_attaches_to_items_that_reference_it() -> None:
    perf = """
      <PerfDescr ID="P1">
       <PerfNo>1</PerfNo>
       <PerfLbl>Notfallplan</PerfLbl>
       <Description><CompleteText>
        <DetailTxt><Text><p><span>Inhalt des Plans.</span></p></Text></DetailTxt>
       </CompleteText></Description>
      </PerfDescr>"""
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", extra='<RefPerfNo IDRef="P1"/>')}
       {perf}
       {_item("20")}
       {_item("30", extra='<RefPerfNo IDRef="P9"/>')}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    result = parse_x83(data)
    items = _by_oz(result)
    assert items["01.0010"].hinweis == "Notfallplan\nInhalt des Plans."
    assert items["01.0020"].hinweis is None
    assert items["01.0030"].hinweis is None
    assert result.remarks == []  # an Ausführungsbeschreibung is not a Hinweis node
    assert result.warnings == ["position 01.0030: RefPerfNo 'P9' names no PerfDescr"]


def test_spans_concatenate_without_separator() -> None:
    # Writers split words across spans (umlauts!); inter-span whitespace is noise.
    detail = """<p>
       <span>Bearbeitete/</span>
       <span>ü</span>
       <span>berarbeitete Datei </span>
       <span>ü</span>
       <span>bergeben.</span>
      </p>"""
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", detail=detail)}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    items = _by_oz(parse_x83(data))
    assert items["01.0010"].langtext == "Bearbeitete/überarbeitete Datei übergeben."


def test_backrefs_resolve_like_d83() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {
            _item(
                "10",
                outline="Suchgraben",
                detail="<p><span>Suchgraben herstellen, Tiefe bis 1,25 m.</span></p>",
            )
        }
       {
            _item(
                "20",
                outline="wie Vorposition",
                detail="<p><span>Leistung wie in voriger Position beschrieben</span><br/><span>jedoch Tiefe bis 1,75 m.</span></p>",
            )
        }
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    items = _by_oz(parse_x83(data))
    linked = items["01.0020"]
    assert linked.linked_oz == "01.0010"
    assert linked.langtext_resolved == (
        "Suchgraben herstellen, Tiefe bis 1,25 m. jedoch Tiefe bis 1,75 m."
    )


def test_provis_maps_to_bedarfsposition() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", extra="<Provis/>")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    items = _by_oz(parse_x83(data))
    assert items["01.0010"].positionstyp == "Bedarfsposition"


def test_blank_qty_reads_as_zero_with_warning() -> None:
    data = _document(
        f"""
    <BoQCtgy RNoPart="1">
     <LblTx><p><span>Bau</span></p></LblTx>
     <BoQBody>
      <Itemlist>
       {_item("10", qty="")}
      </Itemlist>
     </BoQBody>
    </BoQCtgy>"""
    )
    result = parse_x83(data)
    assert result.items[-1].menge == Decimal(0)
    assert any("blank Menge" in warning for warning in result.warnings)


def test_not_gaeb_xml_raises() -> None:
    with pytest.raises(X83ParseError, match="not a GAEB"):
        parse_x83(b"<foo/>")
    with pytest.raises(X83ParseError, match="not well-formed"):
        parse_x83(b"not xml at all")


def test_is_x83_file() -> None:
    assert is_x83_file("P630394379990126_LV.X83")
    assert is_x83_file("projekt_lv.x83")
    assert not is_x83_file("projekt_lv.d83")
    assert not is_x83_file("Projekt_LV1.pdf")


# The real export lives in the untracked eval/context tree; exercise it when present.
_REAL_FILE = (
    Path(__file__).parents[5]
    / "eval"
    / "context"
    / "P630394379990126"
    / "P630394379990126_LV.X83"
)


def test_real_x83_export_parses_clean() -> None:
    if not _REAL_FILE.exists():
        pytest.skip("eval/context fixture not present")
    result = parse_x83(_REAL_FILE.read_bytes())
    assert len(result.items) == 83  # 13 categories + 70 items
    priced = [item for item in result.items if item.positionstyp != "Titel"]
    assert len(priced) == 70
    assert result.warnings == []
    # OZ segments are zero-padded to the BoQBkdn lengths.
    assert result.items[0].oz == "01"
    assert priced[0].oz == "01.01.0010"
    # The umlaut-splitting spans of the Remark survive concatenation.
    governed = [item for item in priced if item.hinweis]
    assert any("überarbeitete" in item.hinweis for item in governed if item.hinweis)
