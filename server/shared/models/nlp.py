"""Domain models for the NLP analysis feature: layout regions, reflowed blocks,
sentences, and POS statistics.

A LayoutRegion is one detected area on a rendered page (Docling label + bbox in
PDF points, top-left origin). A ReflowedBlock is the reflow service's output unit:
typed, ordered text carrying provenance back to the source_lines it was built from.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import BlockType

# Block types included in sentence/POS analysis when a request names none.
DEFAULT_INCLUDE_BLOCKS: tuple[BlockType, ...] = (
    BlockType.PROSE,
    BlockType.HEADING,
    BlockType.LIST_ITEM,
)


class LayoutRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    label: str
    bbox: tuple[float, float, float, float]
    confidence: float | None = None


class DocumentLayout(BaseModel):
    """Cached layout-model output for one document."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    model_version: str
    regions: list[LayoutRegion]


class ReflowedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: int
    block_type: BlockType
    text: str
    page_start: int
    page_end: int
    line_ids: list[int]


class ReflowResult(BaseModel):
    """Reflow output: content blocks plus the classification of every source line
    (including furniture and excluded types) for the original-lines view."""

    model_config = ConfigDict(extra="forbid")

    blocks: list[ReflowedBlock]
    line_types: dict[int, BlockType]


class SentenceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_hash: str
    block_id: int
    text: str


class TokenInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    lemma: str
    sentence_hash: str


class PosTagStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    count: int
    percentage: float
    tokens: list[TokenInfo]


class PosStats(BaseModel):
    """POS distribution at both granularities: coarse UD (pos_) and fine STTS (tag_)."""

    model_config = ConfigDict(extra="forbid")

    token_count: int
    ud: list[PosTagStats]
    stts: list[PosTagStats]
