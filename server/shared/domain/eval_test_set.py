from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewEvalTestSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class EvalTestSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_set_uuid: UUID
    name: str
    description: str | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
