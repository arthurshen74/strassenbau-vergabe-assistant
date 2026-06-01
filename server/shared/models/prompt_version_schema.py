"""API schemas for the PromptVersion resource: Create / Read.

Mirrors models/prompt_version.py. PromptVersions are immutable and append-only;
there is no Update DTO. `PromptVersionCreate` matches the repository's
`NewPromptVersion` create-model (the repository assigns `version`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import PromptType


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    prompt_version_uuid: UUID
    prompt_type: PromptType
    version: int
    model_name: str
    system_prompt: str
    temperature: float | None = None
    top_p: float | None = None
    created_at: datetime


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_type: PromptType
    model_name: str
    system_prompt: str
    temperature: float | None = 0.0
    top_p: float | None = None
