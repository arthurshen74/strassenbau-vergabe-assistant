"""API schemas for the Document resource: Create / Read.

Mirrors the domain model in models/document.py as a separate boundary type family.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import DocumentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    document_type: DocumentType
    file_name: str
    document_description: str | None = None
    number_of_pages: int


class DocumentDetailRead(BaseModel):
    """The Projects document-detail header: metadata + chunk counts per source."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    file_name: str
    document_type: DocumentType
    number_of_pages: int
    upload_date: datetime
    last_ingest_date: datetime | None = None
    simple_chunk_count: int
    langchain_chunk_count: int


class ChunkRead(BaseModel):
    """One chunk for the document chunk viewer, unified across the Simple and LangChain indexes."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source: Literal["simple", "langchain"]
    source_doc_type: str | None = None  # DOCUMENT | LV_ITEM (simple); None (langchain)
    chunk_index: int | None = None  # SimpleChunk index; None for langchain (positional)
    page: int | None = None  # langchain page; None for simple
    oz: str | None = None
    stl_nr: str | None = None
    pages: list[int] = []  # simple source_doc_pages; [] for langchain
    text: str


class ChunkListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChunkRead]
    total: int
