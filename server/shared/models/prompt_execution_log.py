from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptExecutionLog(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    log_uuid: UUID
    prompt_type: str | None = None
    prompt_version: int | None = None
    model: str
    provider_url: str | None = None
    system_prompt: str | None = None
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    response_text: str | None = None
    response_tool_calls: list[dict[str, Any]] | None = None
    response_structured: dict[str, Any] | None = None
    finish_reason: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    request_id: str | None = None
    project_uuid: UUID | None = None
    ingest_job_uuid: UUID | None = None
    conversation_uuid: UUID | None = None
    success: bool
    error_message: str | None = None
    sent_at: datetime | None = None
    returned_at: datetime | None = None
    created_at: datetime


class NewPromptExecutionLog(BaseModel):
    """Shape required to record an execution-log row. PK and created_at assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[dict[str, Any]]
    success: bool
    prompt_type: str | None = None
    prompt_version: int | None = None
    provider_url: str | None = None
    system_prompt: str | None = None
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    response_text: str | None = None
    response_tool_calls: list[dict[str, Any]] | None = None
    response_structured: dict[str, Any] | None = None
    finish_reason: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    request_id: str | None = None
    project_uuid: UUID | None = None
    ingest_job_uuid: UUID | None = None
    conversation_uuid: UUID | None = None
    error_message: str | None = None
    sent_at: datetime | None = None
    returned_at: datetime | None = None
