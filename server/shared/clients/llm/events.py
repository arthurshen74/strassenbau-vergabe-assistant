"""Events yielded by `LLMClient.stream_chat`.

A stream yields zero or more `TextDelta` as content arrives, then (if the model called
tools) one `ToolCallsReady` with the fully-assembled calls, then a final `Done` with the
finish reason. Tool-call fragments are assembled inside the client so consumers receive
whole calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: str  # raw JSON string, parsed by the consumer


class TextDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class ToolCallsReady(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ToolCall]


class Done(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finish_reason: str | None = None


StreamEvent = TextDelta | ToolCallsReady | Done
