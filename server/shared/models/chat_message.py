from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    """A seed message stored on a PromptVersion (JSONB), not its own table."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
