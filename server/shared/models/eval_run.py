"""Domain models for eval runs: the queued/graded run itself, its progress events, and the
per-item result rows. The queue mechanics mirror ingest jobs; see shared.services.eval."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import EvalRunKind, EvalRunStatus


class EvalRunCreate(BaseModel):
    """POST body: which grader to run, on what scope, with which knobs."""

    model_config = ConfigDict(extra="forbid")

    kind: EvalRunKind
    project_uuid: UUID | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class NewEvalRun(EvalRunCreate):
    """Insert model. PK, status, and timestamps assigned by the DB."""

    created_by_user_id: UUID


class EvalRun(NewEvalRun):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    eval_run_uuid: UUID
    status: EvalRunStatus
    locked_at: datetime | None = None
    locked_by: str | None = None
    attempts: int = 0
    error: str | None = None
    summary: dict[str, Any] | None = None
    prompt_versions: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EvalRunEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    event_uuid: UUID
    eval_run_uuid: UUID
    message: str
    ts: datetime


class EvalResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    result_uuid: UUID
    eval_run_uuid: UUID
    item_id: str
    payload: dict[str, Any]
    created_at: datetime
