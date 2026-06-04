"""API schemas for the Conversation resource. The owner (`user_uuid`) is taken from the
authenticated principal, not the request body, so it is absent from `ConversationCreate`."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import PromptType


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    conversation_uuid: UUID
    user_uuid: UUID
    project_uuid: UUID | None = None
    prompt_type: PromptType
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_type: PromptType
    project_uuid: UUID | None = None
    title: str | None = None


class ConversationCostRead(BaseModel):
    """Total USD cost attributed to a conversation so far."""

    model_config = ConfigDict(extra="forbid")

    conversation_uuid: UUID
    cost: Decimal
