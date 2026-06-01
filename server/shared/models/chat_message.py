from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    """A single user/assistant turn passed to the LLM transport."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
