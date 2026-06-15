from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import CalculationStatus, PromptType


class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    conversation_uuid: UUID
    user_uuid: UUID
    project_uuid: UUID | None = None
    prompt_type: PromptType
    calculation_status: CalculationStatus | None = None
    lv_item_uuid: UUID | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class NewConversation(BaseModel):
    """Create-model for a conversation. PK and timestamps assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    user_uuid: UUID
    prompt_type: PromptType
    project_uuid: UUID | None = None
    calculation_status: CalculationStatus | None = None
    lv_item_uuid: UUID | None = None
    title: str | None = None
