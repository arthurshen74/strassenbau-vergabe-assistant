from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import MessageKind


class Message(BaseModel):
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


class NewMessage(BaseModel):
    """Create-model for a message. PK and created_at assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    conversation_uuid: UUID
    kind: MessageKind
    content: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    success: bool | None = None
    data: dict[str, Any] | None = None
    errors: list[str] | None = None
