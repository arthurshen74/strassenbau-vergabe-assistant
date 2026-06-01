"""The execution-log event a chat/stream call emits at the LLMClient boundary.

Transport-neutral, like `UsageEvent` for usage. A sink turns it into a persisted row (or a
log line). Captures the full request and response so a call can be inspected after the fact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExecutionLogEvent(BaseModel):
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
    error_message: str | None = None
    sent_at: datetime | None = None
    returned_at: datetime | None = None
