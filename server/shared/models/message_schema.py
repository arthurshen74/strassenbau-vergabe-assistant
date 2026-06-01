"""API schema for reading messages. Messages are created by the dispatcher, not via a request
body, so there is no MessageCreate DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import MessageKind


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    message_uuid: UUID
    conversation_uuid: UUID
    kind: MessageKind
    content: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    success: bool | None = None
    data: dict[str, Any] | None = None
    errors: list[str] | None = None
    created_at: datetime
