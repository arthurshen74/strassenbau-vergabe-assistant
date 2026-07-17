from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import PromptType


class PromptVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    prompt_version_uuid: UUID
    prompt_type: PromptType
    version: int
    model_name: str
    system_prompt: str
    temperature: float | None = None
    top_p: float | None = None
    reasoning_effort: str | None = None
    created_at: datetime


class NewPromptVersion(BaseModel):
    """Create-model for a prompt version. `version` is assigned by the repository (next
    integer for the prompt_type); PK and created_at by the DB."""

    model_config = ConfigDict(extra="forbid")

    prompt_type: PromptType
    model_name: str
    system_prompt: str
    temperature: float | None = 0.0
    top_p: float | None = None
    reasoning_effort: str | None = None
