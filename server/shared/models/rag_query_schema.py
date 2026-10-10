"""API schemas for the RagQueryVersion resource: Create / Read.

Mirrors models/rag_query.py. RAG query versions are immutable and append-only; there is
no Update DTO. The `query_key` of a create comes from the URL path, not the body.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.config import settings
from shared.models.enums import ProjectInfoQuery

# ISO 639-1, lower case; mirrors the rag_query_versions CHECK.
LANGUAGE_PATTERN = r"^[a-z]{2}$"


class RagQueryVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    rag_query_version_uuid: UUID
    query_key: ProjectInfoQuery
    language: str
    version: int
    name: str
    description: str
    query_text: str
    answer_instruction: str
    created_at: datetime


class RagQueryVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(
        default_factory=lambda: settings.project_info_language,
        pattern=LANGUAGE_PATTERN,
    )
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    answer_instruction: str = Field(min_length=1)
