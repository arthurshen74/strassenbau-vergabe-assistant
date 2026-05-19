from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_item_uuid: UUID
    test_set_uuid: UUID
    actual_result: Any | None = None
    passed: bool
    metrics: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_result_uuid: UUID
    eval_item_uuid: UUID
    test_set_uuid: UUID
    ran_at: datetime
    actual_result: Any | None
    passed: bool
    metrics: dict[str, Any]
