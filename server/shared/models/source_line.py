from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SourceLine(BaseModel):
    """Canonical per-line text for a document; the verbatim source the rest of the
    pipeline slices from (chunks, LV item bodies). No timestamps in the schema."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    source_line_uuid: UUID
    document_uuid: UUID
    line_id: int
    page: int
    bbox: tuple[float, float, float, float]
    line_text: str


class NewSourceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    line_id: int
    page: int
    bbox: tuple[float, float, float, float]
    line_text: str
