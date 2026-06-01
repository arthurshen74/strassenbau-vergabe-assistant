from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import UsageOperation


class OpenRouterUsage(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    usage_uuid: UUID
    operation: UsageOperation
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    search_units: int | None = None
    project_uuid: UUID | None = None
    ingest_job_uuid: UUID | None = None
    request_id: str | None = None
    chat_prompt_type: str | None = None
    chat_prompt_version: int | None = None
    created_at: datetime


class NewOpenRouterUsage(BaseModel):
    """Shape required to record a usage row. PK and created_at assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    operation: UsageOperation
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    search_units: int | None = None
    project_uuid: UUID | None = None
    ingest_job_uuid: UUID | None = None
    request_id: str | None = None
    chat_prompt_type: str | None = None
    chat_prompt_version: int | None = None
