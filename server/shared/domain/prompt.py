from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NewPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    description: str | None = None
    is_archived: bool = False


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_uuid: UUID
    slug: str
    description: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
