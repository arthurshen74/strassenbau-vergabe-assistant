"""Internal value types for LV post-processing.

`ParsedPosition` is the LLM segmentation normalised off the wire schema;
`SlicedPosition` adds the verbatim text and pages sliced from SourceLine; `ResolvedItem`
is one fully-built item ready for persistence (`build_resolved_item` constructs it from
a sliced position and its links). `LVParseResult` is the stage output.

The GAEB readers also emit the LV's free text outside the positions: `AddTextBlock` is a
Zusaetzlicher Text (GAEB 90 `T0`..`T9` block, GAEB DA XML `AddText`) placed before or
after the BoQ, the spec's home for Vorbemerkungen and Nachtext; `Remark` is a
Hinweistext (GAEB 90 record `20`, XML `Remark`) that lives inside the LV hierarchy. A
Remark records only what the file states with certainty, its structural parent and its
sequence within that parent; a semantic target ("applies to position X") is undecidable
for a mid-group Hinweis and is deliberately not modelled."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from shared.models.enums import LVTextKind, LVTextPlacement
from shared.models.llm_output_schemas.lv_extraction import POSITIONSTYP_TITEL
from shared.models.lv_item import NewLVItem
from shared.models.lv_text import NewLVText

TITEL_MENGE = Decimal(0)


@dataclass(frozen=True)
class ParsedPosition:
    """One position as the LLM segmented it: line references plus verbatim header
    tokens.

    Body/hinweis are explicit sorted line_id lists (not a single span) so that
    coalescing duplicate entries for one OZ can take the union of their lines."""

    oz: str
    is_title: bool
    kurztext_line: int
    langtext_lines: list[int]
    hinweis_lines: list[int]
    stl_nr: str | None
    menge: str | None
    einheit: str | None
    linked_oz: str | None
    positionstyp: str | None


@dataclass(frozen=True)
class SlicedPosition:
    """A position with its verbatim text sliced out of SourceLine and pages resolved."""

    oz: str
    is_title: bool
    kurztext: str
    langtext: str
    hinweis: str | None
    menge: str | None
    einheit: str | None
    stl_nr: str | None
    linked_oz: str | None
    positionstyp: str | None
    pages: list[int]
    source_line_uuids: list[UUID]


@dataclass(frozen=True)
class LinkInfo:
    """Hierarchy and ordering links derived from the OZ sequence."""

    level: int
    parent_oz: str | None
    prev_oz: str | None
    next_oz: str | None


@dataclass(frozen=True)
class ResolvedItem:
    """A fully composed LV item, pre-persistence."""

    oz: str
    kurztext: str
    langtext: str
    langtext_resolved: str | None
    menge: Decimal
    einheit: str
    positionstyp: str | None
    level: int | None
    stl_nr: str | None
    hinweis: str | None
    linked_oz: str | None
    prev_oz: str | None
    next_oz: str | None
    parent_oz: str | None
    pages: list[int]
    source_line_uuids: list[UUID]


def build_resolved_item(
    position: SlicedPosition,
    menge: Decimal,
    langtext_resolved: str | None,
    link: LinkInfo,
) -> ResolvedItem:
    """One ResolvedItem from a sliced position and its links. A title carries no
    quantity; it is persisted with menge 0 and a Titel type so it is still addressable
    by OZ and retrievable as an LV_ITEM chunk."""
    if position.is_title:
        menge = TITEL_MENGE
        positionstyp: str | None = POSITIONSTYP_TITEL
    else:
        positionstyp = position.positionstyp

    return ResolvedItem(
        oz=position.oz,
        kurztext=position.kurztext,
        langtext=position.langtext or position.kurztext,
        langtext_resolved=langtext_resolved,
        menge=menge,
        einheit=position.einheit or "",
        positionstyp=positionstyp,
        level=link.level,
        stl_nr=position.stl_nr,
        hinweis=position.hinweis,
        linked_oz=position.linked_oz,
        prev_oz=link.prev_oz,
        next_oz=link.next_oz,
        parent_oz=link.parent_oz,
        pages=position.pages,
        source_line_uuids=position.source_line_uuids,
    )


@dataclass(frozen=True)
class AddTextBlock:
    """One Zusaetzlicher Text block outside the LV hierarchy; applies to the whole LV
    by construction. `heading` is the XML OutlineAddText (GAEB 90 T-lines have none);
    `order` is the document order within its placement."""

    placement: LVTextPlacement
    heading: str | None
    body: str
    order: int


@dataclass(frozen=True)
class Remark:
    """One Hinweistext node in the LV tree. `parent_oz` is the enclosing LV-Gruppe
    (None at the LV root); `index` is the node's ordinal among that parent's direct
    children (groups, positions and Hinweise) in document order. `oz` is the optional
    identifier from the record (blank `20` / missing `RNoPart` -> None); it is not a
    scope pointer."""

    oz: str | None
    heading: str | None
    body: str
    parent_oz: str | None
    index: int

    @property
    def text(self) -> str:
        return hinweis_text(self.heading, self.body)


def hinweis_text(heading: str | None, body: str) -> str:
    """A Hinweis as one text block: heading line plus body, unless the body already
    opens with the heading (X83 writers repeat the Kurztext there)."""
    if not heading:
        return body
    if not body:
        return heading
    if body.lower().startswith(heading.lower()):
        return body
    return f"{heading}\n{body}"


@dataclass(frozen=True)
class LVParseResult:
    """The LV parse output: one ResolvedItem per position, the LV-level free text, every
    Hinweistext node, plus soft validation warnings."""

    items: list[ResolvedItem]
    warnings: list[str]
    add_texts: list[AddTextBlock] = field(default_factory=list)
    remarks: list[Remark] = field(default_factory=list)

    def vortext(self) -> list[AddTextBlock]:
        return [b for b in self.add_texts if b.placement is LVTextPlacement.BEFORE_BOQ]

    def nachtext(self) -> list[AddTextBlock]:
        return [b for b in self.add_texts if b.placement is LVTextPlacement.AFTER_BOQ]

    def leading_root_remarks(self) -> list[Remark]:
        """Root-level Hinweise that precede the first LV-Gruppe or position: the place
        AVA tools print as "Vorbemerkungen" when the author never used a Zusaetzlicher
        Text. A view next to `vortext()`, not merged into it."""
        leading: list[Remark] = []
        for remark in self.remarks:
            if remark.parent_oz is None and remark.index == len(leading):
                leading.append(remark)
        return leading

    def to_new_lv_items(self, document_uuid: UUID) -> list[NewLVItem]:
        return [
            NewLVItem(
                document_uuid=document_uuid,
                oz=item.oz,
                kurztext=item.kurztext,
                langtext=item.langtext,
                langtext_resolved=item.langtext_resolved,
                menge=item.menge,
                einheit=item.einheit,
                positionstyp=item.positionstyp,
                level=item.level,
                stl_nr=item.stl_nr,
                hinweis=item.hinweis,
                linked_oz=item.linked_oz,
                prev_oz=item.prev_oz,
                next_oz=item.next_oz,
                parent_oz=item.parent_oz,
                source_lines=item.source_line_uuids,
            )
            for item in self.items
        ]

    def to_new_lv_texts(self, document_uuid: UUID) -> list[NewLVText]:
        """Vortext blocks, every Hinweistext node, then Nachtext blocks: the LV's
        document order, stamped as `sequence`."""
        rows: list[NewLVText] = []
        for block in self.vortext() + self.nachtext():
            rows.append(
                NewLVText(
                    document_uuid=document_uuid,
                    kind=LVTextKind.ADD_TEXT,
                    placement=block.placement,
                    index=block.order,
                    sequence=len(rows),
                    heading=block.heading,
                    body=block.body,
                )
            )
        remarks = [
            NewLVText(
                document_uuid=document_uuid,
                kind=LVTextKind.REMARK,
                parent_oz=remark.parent_oz,
                index=remark.index,
                sequence=0,
                oz=remark.oz,
                heading=remark.heading,
                body=remark.body,
            )
            for remark in self.remarks
        ]
        before = [r for r in rows if r.placement is LVTextPlacement.BEFORE_BOQ]
        after = [r for r in rows if r.placement is LVTextPlacement.AFTER_BOQ]
        ordered = before + remarks + after
        return [
            row.model_copy(update={"sequence": sequence})
            for sequence, row in enumerate(ordered)
        ]
