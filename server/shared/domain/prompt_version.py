from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NewPromptVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    model_provider: str
    model_id: str
    model_endpoint: str | None = None
    api_key_ref: str
    temperature: float
    top_p: float | None = None
    max_tokens: int
    stop_sequences: list[str] | None = None
    output_schema_ref: str | None = None
    tool_selection: list[str] | None = None


class PromptVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_uuid: UUID
    prompt_uuid: UUID
    version: int
    system_prompt: str
    model_provider: str
    model_id: str
    model_endpoint: str | None
    api_key_ref: str
    temperature: float
    top_p: float | None
    max_tokens: int
    stop_sequences: list[str] | None
    output_schema_ref: str | None
    tool_selection: list[str] | None
    created_at: datetime
