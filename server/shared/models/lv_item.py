from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LVItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    lv_item_uuid: UUID
    document_uuid: UUID
    oz: str
    kurztext: str
    langtext: str
    langtext_resolved: str | None = None
    menge: Decimal
    einheit: str
    positionstyp: str | None = None
    level: int | None = None
    stl_nr: str | None = None
    hinweis: str | None = None
    linked_oz: str | None = None
    prev_oz: str | None = None
    next_oz: str | None = None
    parent_oz: str | None = None
    source_lines: list[UUID] = Field(default_factory=list)
    last_ingestion: datetime


class NewLVItem(BaseModel):
    """Shape required to create an LVItem. PK and last_ingestion assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    oz: str
    kurztext: str
    langtext: str
    langtext_resolved: str | None = None
    menge: Decimal
    einheit: str
    positionstyp: str | None = None
    level: int | None = None
    stl_nr: str | None = None
    hinweis: str | None = None
    linked_oz: str | None = None
    prev_oz: str | None = None
    next_oz: str | None = None
    parent_oz: str | None = None
    source_lines: list[UUID] = Field(default_factory=list)
