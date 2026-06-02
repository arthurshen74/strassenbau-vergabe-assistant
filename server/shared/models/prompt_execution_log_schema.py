"""API schemas for the prompt execution log.

`PromptExecutionLogSummary` backs the table listing (small, no heavy JSON payloads);
`PromptExecutionLogRead` is the full row for the detail view. Both mirror
models/prompt_execution_log.py as a separate boundary type family.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PromptExecutionLogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    log_uuid: UUID
    prompt_type: str | None = None
    prompt_version: int | None = None
    model: str
    success: bool
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None
    error_message: str | None = None
    created_at: datetime


class PromptExecutionLogRead(BaseModel):
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
    success: bool
    error_message: str | None = None
    sent_at: datetime | None = None
    returned_at: datetime | None = None
    created_at: datetime
