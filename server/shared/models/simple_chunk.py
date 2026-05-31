from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import SourceDocType


class SimpleChunk(BaseModel):
    """The Elasticsearch document shape. `source_doc_uuid` resolves to a Document or
    LVItem depending on `source_doc_type`."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    chunk_uuid: UUID
    source_doc_uuid: UUID
    source_doc_type: SourceDocType
    source_doc_field: str
    source_doc_language: str = "de"
    source_doc_pages: list[int] = Field(default_factory=list)
    chunk_index: int
    oz: str | None = None
    stl_nr: str | None = None
    project_uuid: UUID
    chunk_text: str
    embedding: list[float]
    embedding_model: str


class NewSimpleChunk(BaseModel):
    """Create-model for indexing. chunk_uuid is assigned at index time by the search client."""

    model_config = ConfigDict(extra="forbid")

    source_doc_uuid: UUID
    source_doc_type: SourceDocType
    source_doc_field: str
    source_doc_language: str = "de"
    source_doc_pages: list[int] = Field(default_factory=list)
    chunk_index: int
    oz: str | None = None
    stl_nr: str | None = None
    project_uuid: UUID
    chunk_text: str
    embedding: list[float]
    embedding_model: str
