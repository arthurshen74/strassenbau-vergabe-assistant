"""Pydantic models for the Neo4j construction knowledge graph.

These are the write-path schema enforcement for the graph nodes: Neo4j Community
enforces only uniqueness natively, so all other invariants (enum membership,
embedding dimension, page-range ordering) are validated here before any Cypher
runs. Canonical schema: docs/DATA_MODEL.md §7. Node ids (project_uuid,
document_id, oz, chunk_id) are stored as strings in Neo4j; the UUID-typed,
embedding-free domain models live under shared/domain/.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from shared.config import settings


class PositionsTyp(StrEnum):
    NORMAL = "normal"
    BEDARF = "bedarf"
    WAHL = "wahl"
    ZULAGE = "zulage"
    PAUSCHAL = "pauschal"


class ChunkType(StrEnum):
    SIMPLE = "simple"
    PROSE = "prose"


def _check_embedding_dim(v: list[float] | None) -> list[float] | None:
    if v is not None and len(v) != settings.embedding_dim:
        raise ValueError(
            f"embedding must have dimension {settings.embedding_dim}, got {len(v)}"
        )
    return v


Embedding = Annotated[list[float] | None, AfterValidator(_check_embedding_dim)]


def _check_page_range(start: int, end: int) -> None:
    if end < start:
        raise ValueError(
            f"page_number_end ({end}) must be >= page_number_start ({start})"
        )


class Project(BaseModel):
    """Graph anchor; Postgres `projects` is the identity record."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: str


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    project_uuid: str
    document_kind: str
    total_pages: int = Field(ge=1)


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    project_uuid: str
    page_number: int = Field(ge=1)


class Section(BaseModel):
    """Heading/group node shared by both ingest paths; keyed on `oz`."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    project_uuid: str
    oz: str
    title: str
    level: int = Field(ge=1)


class LVItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    project_uuid: str
    oz: str
    kurztext: str
    langtext: str
    menge: Decimal | None = None
    einheit: str | None = None
    positionstyp: PositionsTyp
    level: int = Field(ge=1)
    stl_nr: str | None = None
    page_number_start: int = Field(ge=1)
    page_number_end: int = Field(ge=1)
    ordinal: int = Field(ge=0)
    embedding: Embedding = None

    @model_validator(mode="after")
    def _validate_page_range(self) -> LVItem:
        _check_page_range(self.page_number_start, self.page_number_end)
        return self


class SimpleChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    project_uuid: str
    text: str
    page_number_start: int = Field(ge=1)
    page_number_end: int = Field(ge=1)
    ordinal: int = Field(ge=0)
    start_index: int = Field(ge=0)
    embedding: Embedding = None

    @model_validator(mode="after")
    def _validate_page_range(self) -> SimpleChunk:
        _check_page_range(self.page_number_start, self.page_number_end)
        return self


class ProseChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    project_uuid: str
    text: str
    page_number_start: int = Field(ge=1)
    page_number_end: int = Field(ge=1)
    ordinal: int = Field(ge=0)
    section_oz: str
    heading: str
    breadcrumb: str
    part: int = Field(ge=0)
    embedding: Embedding = None

    @model_validator(mode="after")
    def _validate_page_range(self) -> ProseChunk:
        _check_page_range(self.page_number_start, self.page_number_end)
        return self
