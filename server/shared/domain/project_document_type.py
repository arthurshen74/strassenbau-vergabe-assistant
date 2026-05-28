from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FormTypeStandard(StrEnum):
    HVA_STB = "HVA StB"
    VHB = "VHB"


class NewProjectDocumentType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    document_type_description: str | None = None
    form_type_standard: FormTypeStandard | None = None
    form_type_number: int | None = None


class ProjectDocumentType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type_uuid: UUID
    document_type: str
    document_type_description: str | None
    form_type_standard: FormTypeStandard | None
    form_type_number: int | None
