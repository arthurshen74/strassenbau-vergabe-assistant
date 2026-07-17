"""Unit tests for the Docling region mapping (no model, fake DoclingDocument objects)."""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.services.nlp.layout import regions_from_docling


@dataclass
class _Bbox:
    l: float
    t: float
    r: float
    b: float

    def to_top_left_origin(self, page_height: float) -> _Bbox:
        # Mimics docling's BOTTOMLEFT -> TOPLEFT conversion.
        return _Bbox(self.l, page_height - self.t, self.r, page_height - self.b)


@dataclass
class _Prov:
    page_no: int
    bbox: _Bbox


@dataclass
class _Size:
    width: float
    height: float


@dataclass
class _Page:
    size: _Size


@dataclass
class _Item:
    label: str
    prov: list[_Prov]


@dataclass
class _Doc:
    texts: list[_Item]
    tables: list[_Item] = field(default_factory=list)
    pictures: list[_Item] = field(default_factory=list)
    pages: dict[int, _Page] = field(default_factory=dict)


def test_regions_mapped_with_top_left_origin() -> None:
    doc = _Doc(
        texts=[_Item("page_header", [_Prov(1, _Bbox(10.0, 800.0, 200.0, 780.0))])],
        tables=[_Item("table", [_Prov(2, _Bbox(50.0, 500.0, 550.0, 100.0))])],
        pages={1: _Page(_Size(595.0, 842.0)), 2: _Page(_Size(595.0, 842.0))},
    )

    regions = regions_from_docling(doc)

    assert [r.label for r in regions] == ["page_header", "table"]
    header = regions[0]
    assert header.page == 1
    # y flips: bbox top (800 from bottom) becomes 42 from top of an 842pt page.
    assert header.bbox == (10.0, 42.0, 200.0, 62.0)


def test_multi_prov_item_yields_region_per_page() -> None:
    item = _Item(
        "text",
        [
            _Prov(1, _Bbox(0.0, 100.0, 100.0, 50.0)),
            _Prov(2, _Bbox(0.0, 800.0, 100.0, 750.0)),
        ],
    )
    doc = _Doc(
        texts=[item],
        pages={1: _Page(_Size(595.0, 842.0)), 2: _Page(_Size(595.0, 842.0))},
    )

    regions = regions_from_docling(doc)

    assert [r.page for r in regions] == [1, 2]
