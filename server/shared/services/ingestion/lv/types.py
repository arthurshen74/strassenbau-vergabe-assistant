"""Internal value types for LV post-processing.

`ParsedPosition` is the LLM segmentation normalised off the wire schema; `SlicedPosition`
adds the verbatim text and pages sliced from SourceLine; `ResolvedItem` is one fully-built
item ready for persistence (`build_resolved_item` constructs it from a sliced position and
its links). `LVParseResult` is the stage output."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from shared.models.llm_output_schemas.lv_extraction import POSITIONSTYP_TITEL
from shared.models.lv_item import NewLVItem

TITEL_MENGE = Decimal(0)


@dataclass(frozen=True)
class ParsedPosition:
    """One position as the LLM segmented it: line references plus verbatim header tokens.

    Body/hinweis are explicit sorted line_id lists (not a single span) so that coalescing
    duplicate entries for one OZ can take the union of their lines."""

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
    """One ResolvedItem from a sliced position and its links. A title carries no quantity;
    it is persisted with menge 0 and a Titel type so it is still addressable by OZ and
    retrievable as an LV_ITEM chunk."""
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
class LVParseResult:
    """The LV parse output: one ResolvedItem per position, plus soft validation warnings."""

    items: list[ResolvedItem]
    warnings: list[str]

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
