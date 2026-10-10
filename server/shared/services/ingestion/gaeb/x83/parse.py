"""GAEB DA XML X83 reader: walk the Award into LV items and LV-level texts.

`AddText` elements beside the `BoQ` are the Zusaetzlichen Texte: Vortext before the BoQ,
Nachtext after it, with document order as the only signal. Inside the BoQ, `BoQCtgy`
elements become Titel items, `Itemlist/Item` elements priced positions, and `Remark`
elements `Remark` nodes under their containing BoQBody. A position's `hinweis` is the
positional projection of those nodes (every Remark in the enclosing containers that
precedes it, outermost first) plus any Ausfuehrungsbeschreibung (`PerfDescr`) the item
references through `RefPerfNo`. Text bodies keep only the markup that matters -- `span`
text concatenates verbatim, `br` breaks a line, each `p` is a line of its own -- while
whitespace-only text nodes between elements are pretty-printing noise. OZ segments are
zero-padded to the BoQBkdn lengths so OZ strings sort and link exactly like their D83
counterparts (e.g. '01.02.0030').
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from shared.models.llm_output_schemas.lv_extraction import (
    POSITIONSTYP_ALTERNATIV,
    POSITIONSTYP_BEDARF,
    POSITIONSTYP_GRUND,
    POSITIONSTYP_NORMAL,
)
from shared.services.ingestion.gaeb.compose import (
    OZ_SEGMENT_SEP,
    GaebParseError,
    RawLVItem,
    compose,
)
from shared.services.ingestion.lv.types import (
    AddTextBlock,
    LVParseResult,
    LVTextPlacement,
    Remark,
    hinweis_text,
)

GAEB_X83_SUFFIX = ".x83"
GAEB_XML_NAMESPACE_PREFIX = "http://www.gaeb.de/GAEB_DA_XML/"
DA83_NAMESPACE_PART = "/DA83/"

HINWEIS_BLOCK_SEP = "\n\n"
KURZTEXT_JOIN = " "

TAG_AWARD = "Award"
TAG_ADD_TEXT = "AddText"
TAG_OUTLINE_ADD_TEXT = "OutlineAddText"
TAG_DETAIL_ADD_TEXT = "DetailAddText"
TAG_BOQ = "BoQ"
TAG_BOQ_INFO = "BoQInfo"
TAG_BOQ_BKDN = "BoQBkdn"
TAG_BOQ_BODY = "BoQBody"
TAG_CTGY = "BoQCtgy"
TAG_ITEMLIST = "Itemlist"
TAG_ITEM = "Item"
TAG_REMARK = "Remark"
TAG_PERF_DESCR = "PerfDescr"
TAG_PERF_LBL = "PerfLbl"
TAG_REF_PERF_NO = "RefPerfNo"
TAG_LBL = "LblTx"
TAG_QTY = "Qty"
TAG_QU = "QU"
TAG_DESCRIPTION = "Description"
TAG_COMPLETE_TEXT = "CompleteText"
TAG_OUTLINE_TEXT = "OutlineText"
TAG_DETAIL_TEXT = "DetailTxt"
TAG_STL_NO = "StLNo"
TAG_PROVIS = "Provis"
TAG_ALN_GROUP_NO = "ALNGroupNo"
TAG_ALN_SER_NO = "ALNSerNo"
TAG_P = "p"
TAG_SPAN = "span"
TAG_BR = "br"

ATTR_RNO_PART = "RNoPart"
ATTR_RNO_INDEX = "RNoIndex"
ATTR_ID = "ID"
ATTR_ID_REF = "IDRef"

BKDN_TYPE = "Type"
BKDN_LENGTH = "Length"
BKDN_TYPE_LEVEL = "BoQLevel"
BKDN_TYPE_ITEM = "Item"


class X83ParseError(GaebParseError):
    """The file violates the GAEB DA XML structure."""


def is_x83_file(file_name: str) -> bool:
    return file_name.lower().endswith(GAEB_X83_SUFFIX)


def parse_x83(data: bytes) -> LVParseResult:
    """Parse X83 bytes into the LVParseResult shape shared with the LV ingestion
    path."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise X83ParseError(f"not well-formed XML: {exc}") from exc
    return compose(*_Reader(root).read())


@dataclass
class _Scope:
    """An open BoQ container (the root BoQBody or a BoQCtgy): the Remarks filed
    directly under it so far and the running count of its direct children."""

    parent_oz: str | None
    remarks: list[Remark] = field(default_factory=list)
    child_count: int = 0


class _Reader:
    def __init__(self, root: ET.Element) -> None:
        self._ns = _namespace(root)
        self._root = root
        self._items: list[RawLVItem] = []
        self._warnings: list[str] = []
        self._add_texts: list[AddTextBlock] = []
        self._remarks: list[Remark] = []
        self._perf_texts: dict[str, str] = {}
        self._level_lengths: list[int] = []
        self._item_length: int | None = None
        if DA83_NAMESPACE_PART not in self._ns:
            self._warnings.append(f"namespace {self._ns!r} parsed as DA83")

    def read(
        self,
    ) -> tuple[list[RawLVItem], list[str], list[AddTextBlock], list[Remark]]:
        award = self._root.find(self._tag(TAG_AWARD))
        container = award if award is not None else self._root
        boq_seen = False
        for child in container:
            tag = _local(child.tag)
            if tag == TAG_BOQ:
                if boq_seen:
                    self._warnings.append("second BoQ element ignored")
                    continue
                boq_seen = True
                self._read_boq(child)
            elif tag == TAG_ADD_TEXT:
                self._append_add_text(child, after_boq=boq_seen)
        if not boq_seen:
            raise X83ParseError("no BoQ element")
        return self._items, self._warnings, self._add_texts, self._remarks

    def _tag(self, name: str) -> str:
        return f"{{{self._ns}}}{name}"

    def _read_boq(self, boq: ET.Element) -> None:
        self._read_bkdn(boq)
        for perf in boq.iter(self._tag(TAG_PERF_DESCR)):
            self._read_perf_descr(perf)
        body = boq.find(self._tag(TAG_BOQ_BODY))
        if body is None:
            raise X83ParseError("BoQ has no BoQBody")
        self._read_body(body, segments=(), scopes=[_Scope(parent_oz=None)])

    def _read_bkdn(self, boq: ET.Element) -> None:
        info = boq.find(self._tag(TAG_BOQ_INFO))
        if info is None:
            return
        for bkdn in info.findall(self._tag(TAG_BOQ_BKDN)):
            kind = (bkdn.findtext(self._tag(BKDN_TYPE)) or "").strip()
            length = int((bkdn.findtext(self._tag(BKDN_LENGTH)) or "0").strip() or 0)
            if kind == BKDN_TYPE_LEVEL:
                self._level_lengths.append(length)
            elif kind == BKDN_TYPE_ITEM:
                self._item_length = length

    def _read_perf_descr(self, perf: ET.Element) -> None:
        """An Ausfuehrungsbeschreibung, addressed by ID from the items it covers."""
        perf_id = (perf.get(ATTR_ID) or "").strip()
        heading = (perf.findtext(self._tag(TAG_PERF_LBL)) or "").strip() or None
        body = _block_text(perf.find(f".//{self._tag(TAG_DETAIL_TEXT)}"))
        if not perf_id or not (heading or body):
            return
        self._perf_texts[perf_id] = hinweis_text(heading, body)

    def _append_add_text(self, add_text: ET.Element, *, after_boq: bool) -> None:
        heading = _single_line(
            _block_text(add_text.find(self._tag(TAG_OUTLINE_ADD_TEXT)))
        )
        body = _block_text(add_text.find(self._tag(TAG_DETAIL_ADD_TEXT)))
        if not heading and not body:
            return
        placement = (
            LVTextPlacement.AFTER_BOQ if after_boq else LVTextPlacement.BEFORE_BOQ
        )
        order = sum(1 for block in self._add_texts if block.placement is placement)
        self._add_texts.append(
            AddTextBlock(
                placement=placement, heading=heading or None, body=body, order=order
            )
        )

    def _read_body(
        self, body: ET.Element, segments: tuple[str, ...], scopes: list[_Scope]
    ) -> None:
        for child in body:
            tag = _local(child.tag)
            if tag == TAG_CTGY:
                self._read_ctgy(child, segments, scopes)
            elif tag == TAG_ITEMLIST:
                self._read_itemlist(child, segments, scopes)
            elif tag == TAG_REMARK:
                self._append_remark(child, segments, scopes)

    def _read_ctgy(
        self, ctgy: ET.Element, segments: tuple[str, ...], scopes: list[_Scope]
    ) -> None:
        oz_segments = segments + (self._segment(ctgy, level=len(segments)),)
        oz = OZ_SEGMENT_SEP.join(oz_segments)
        label = _single_line(_block_text(ctgy.find(self._tag(TAG_LBL))))
        scopes[-1].child_count += 1
        self._items.append(
            RawLVItem(
                oz=oz,
                is_title=True,
                kurztext=label,
                langtext="",
                hinweis=None,
                menge=None,
                einheit="",
                stl_nr=None,
                positionstyp=None,
            )
        )
        body = ctgy.find(self._tag(TAG_BOQ_BODY))
        if body is not None:
            self._read_body(body, oz_segments, scopes + [_Scope(parent_oz=oz)])

    def _read_itemlist(
        self, itemlist: ET.Element, segments: tuple[str, ...], scopes: list[_Scope]
    ) -> None:
        for child in itemlist:
            tag = _local(child.tag)
            if tag == TAG_ITEM:
                self._read_item(child, segments, scopes)
            elif tag == TAG_REMARK:
                self._append_remark(child, segments, scopes)
            elif tag != TAG_PERF_DESCR:
                self._warnings.append(f"unsupported Itemlist element {tag!r} ignored")

    def _read_item(
        self, item: ET.Element, segments: tuple[str, ...], scopes: list[_Scope]
    ) -> None:
        oz_segments = segments + (self._segment(item, level=None),)
        index = (item.get(ATTR_RNO_INDEX) or "").strip()
        if index:
            oz_segments += (index,)
        oz = OZ_SEGMENT_SEP.join(oz_segments)
        scopes[-1].child_count += 1

        complete = item.find(
            f"{self._tag(TAG_DESCRIPTION)}/{self._tag(TAG_COMPLETE_TEXT)}"
        )
        kurztext = ""
        langtext = ""
        if complete is not None:
            kurztext = _single_line(
                _block_text(complete.find(self._tag(TAG_OUTLINE_TEXT)))
            )
            langtext = _block_text(complete.find(self._tag(TAG_DETAIL_TEXT)))
        stl_nr = (item.findtext(f".//{self._tag(TAG_STL_NO)}") or "").strip() or None
        blocks = [remark.text for scope in scopes for remark in scope.remarks]
        blocks.extend(self._referenced_perf_texts(item, oz))

        self._items.append(
            RawLVItem(
                oz=oz,
                is_title=False,
                kurztext=kurztext,
                langtext=langtext,
                hinweis=HINWEIS_BLOCK_SEP.join(blocks) or None,
                menge=self._menge(item, oz),
                einheit=(item.findtext(self._tag(TAG_QU)) or "").strip(),
                stl_nr=stl_nr,
                positionstyp=self._positionstyp(item),
            )
        )

    def _referenced_perf_texts(self, item: ET.Element, oz: str) -> list[str]:
        texts: list[str] = []
        for ref in item.findall(self._tag(TAG_REF_PERF_NO)):
            perf_id = (ref.get(ATTR_ID_REF) or "").strip()
            text = self._perf_texts.get(perf_id)
            if text is None:
                self._warnings.append(
                    f"position {oz}: RefPerfNo {perf_id!r} names no PerfDescr"
                )
            else:
                texts.append(text)
        return texts

    def _append_remark(
        self, remark: ET.Element, segments: tuple[str, ...], scopes: list[_Scope]
    ) -> None:
        complete = remark.find(
            f"{self._tag(TAG_DESCRIPTION)}/{self._tag(TAG_COMPLETE_TEXT)}"
        )
        heading = ""
        body = ""
        if complete is not None:
            heading = _single_line(
                _block_text(complete.find(self._tag(TAG_OUTLINE_TEXT)))
            )
            body = _block_text(complete.find(self._tag(TAG_DETAIL_TEXT)))
        if not heading and not body:
            return
        rno = (remark.get(ATTR_RNO_PART) or "").strip()
        oz = None
        if rno:
            if self._item_length and rno.isdigit():
                rno = rno.zfill(self._item_length)
            oz = OZ_SEGMENT_SEP.join(segments + (rno,))
        scope = scopes[-1]
        node = Remark(
            oz=oz,
            heading=heading or None,
            body=body,
            parent_oz=scope.parent_oz,
            index=scope.child_count,
        )
        scope.child_count += 1
        scope.remarks.append(node)
        self._remarks.append(node)

    def _segment(self, element: ET.Element, *, level: int | None) -> str:
        """The element's OZ segment: RNoPart zero-padded to its BoQBkdn length."""
        rno = (element.get(ATTR_RNO_PART) or "").strip()
        if not rno:
            raise X83ParseError(f"{_local(element.tag)} without RNoPart")
        if level is None:
            length = self._item_length
        else:
            length = (
                self._level_lengths[level] if level < len(self._level_lengths) else None
            )
        if length and rno.isdigit():
            return rno.zfill(length)
        return rno

    def _menge(self, item: ET.Element, oz: str) -> Decimal | None:
        qty = (item.findtext(self._tag(TAG_QTY)) or "").strip()
        if not qty:
            return None
        try:
            return Decimal(qty)
        except InvalidOperation as exc:
            raise X83ParseError(f"position {oz}: Qty {qty!r} is not numeric") from exc

    def _positionstyp(self, item: ET.Element) -> str:
        # Best-effort mapping of the optional markers; plain items are Normalpositionen.
        if item.find(self._tag(TAG_PROVIS)) is not None:
            return POSITIONSTYP_BEDARF
        if item.find(self._tag(TAG_ALN_GROUP_NO)) is not None:
            serial = (item.findtext(self._tag(TAG_ALN_SER_NO)) or "").strip()
            return (
                POSITIONSTYP_GRUND
                if serial in ("", "0", "1")
                else POSITIONSTYP_ALTERNATIV
            )
        return POSITIONSTYP_NORMAL


def _namespace(root: ET.Element) -> str:
    tag = root.tag
    if tag.startswith("{"):
        ns = tag[1:].partition("}")[0]
        if ns.startswith(GAEB_XML_NAMESPACE_PREFIX):
            return ns
    raise X83ParseError(f"not a GAEB DA XML document (root {tag!r})")


def _local(tag: str) -> str:
    return tag.partition("}")[2] if tag.startswith("{") else tag


def _block_text(container: ET.Element | None) -> str:
    """The text of a GAEB rich-text container, one line per `p` (plus explicit `br`
    breaks)."""
    if container is None:
        return ""
    paragraphs = [el for el in container.iter() if _local(el.tag) == TAG_P]
    if not paragraphs:
        return _clean_lines(_inline_text(container))
    return _clean_lines("\n".join(_inline_text(p) for p in paragraphs))


def _inline_text(element: ET.Element) -> str:
    """Concatenate the meaningful inline content: span text verbatim, `br` as a newline.

    Whitespace-only text nodes are the writer's pretty-printing, not content (spans
    split words mid-character, e.g. 'Bearbeitete/' + 'ü' + 'berarbeitete'), so they are
    dropped while any non-blank text keeps its original spacing."""
    if _local(element.tag) == TAG_BR:
        return "\n"
    parts: list[str] = []
    if element.text and (_local(element.tag) == TAG_SPAN or element.text.strip()):
        parts.append(element.text)
    for child in element:
        parts.append(_inline_text(child))
        if child.tail and child.tail.strip():
            parts.append(child.tail)
    return "".join(parts)


def _clean_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()).strip("\n")


def _single_line(text: str) -> str:
    return KURZTEXT_JOIN.join(
        line.strip() for line in text.splitlines() if line.strip()
    )
