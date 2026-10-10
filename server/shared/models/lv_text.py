"""LV-level free text of a GAEB LV document, outside the priced positions.

An `LVText` row is either a Zusaetzlicher Text block (`kind` ADD_TEXT: Vortext/Nachtext
by `placement`, ordered by `index` within that placement) or a Hinweistext node (`kind`
REMARK: `parent_oz` is the enclosing LV-Gruppe or None at the LV root, `index` its
ordinal among that parent's direct children). `sequence` is the row's document order
across both kinds. Hinweise are additionally projected onto `lv_items.hinweis`; the rows
here keep the LV-level view and the provenance.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import LVTextKind, LVTextPlacement


class LVText(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    lv_text_uuid: UUID
    document_uuid: UUID
    kind: LVTextKind
    placement: LVTextPlacement | None = None
    parent_oz: str | None = None
    index: int
    sequence: int
    oz: str | None = None
    heading: str | None = None
    body: str
    last_ingestion: datetime


class NewLVText(BaseModel):
    """Shape required to create an LVText. PK and last_ingestion assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    kind: LVTextKind
    placement: LVTextPlacement | None = None
    parent_oz: str | None = None
    index: int
    sequence: int
    oz: str | None = None
    heading: str | None = None
    body: str
