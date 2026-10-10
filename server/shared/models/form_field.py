from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FormField(BaseModel):
    """One field of a fillable form with its filled-in value."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    document_uuid: UUID
    field_order: int
    section: str
    name: str
    label: str | None = None
    value: str
    page: int


class NewFormField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    field_order: int
    section: str
    name: str
    label: str | None = None
    value: str
    page: int
