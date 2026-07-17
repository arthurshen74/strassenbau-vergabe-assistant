"""API schemas for the NLP analysis resource.

Mirrors the domain models in models/nlp.py as boundary types for /nlp/* routes.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from shared.models.enums import BlockType, RenderStyle
from shared.models.nlp import (
    DEFAULT_INCLUDE_BLOCKS,
    PosStats,
    ReflowedBlock,
    SentenceInfo,
)


class NlpDocumentRead(BaseModel):
    """One analyzable document in the modal's picker."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    file_name: str
    project_name: str
    number_of_pages: int


class SourceLineRead(BaseModel):
    """Original extracted line, annotated with its reflow classification."""

    model_config = ConfigDict(extra="forbid")

    line_id: int
    page: int
    text: str
    block_type: BlockType


class DocumentTextRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    blocks: list[ReflowedBlock]
    lines: list[SourceLineRead]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    include_blocks: list[BlockType] = list(DEFAULT_INCLUDE_BLOCKS)

    @field_validator("include_blocks")
    @classmethod
    def furniture_not_analyzable(cls, value: list[BlockType]) -> list[BlockType]:
        if BlockType.FURNITURE in value:
            raise ValueError("FURNITURE blocks are not analyzable")
        if not value:
            raise ValueError("include_blocks must not be empty")
        return value


class RenderRequest(BaseModel):
    """One sentence to render. Text travels in the body (hashes are not reversible);
    the client keys its own cache on the sentence_hash from the analyze response."""

    model_config = ConfigDict(extra="forbid")

    style: RenderStyle
    text: str


class RenderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: RenderStyle
    markup: str


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    include_blocks: list[BlockType]
    sentences: list[SentenceInfo]
    pos: PosStats
