"""Shared shape for dispatcher tools.

A tool is purely declarative: a name + description the LLM sees, a Pydantic input model
(the function parameters), and an async handler that executes it. Handlers run via
**direct service calls** (no HTTP loopback) using the repositories on the
`ToolContext`'s `UnitOfWork`; they carry no business logic of their own beyond shaping
the result into a JSON-serializable dict.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from shared.db.unit_of_work import UnitOfWork

# OpenAI/OpenRouter tools[] entry keys.
TOOL_TYPE = "type"
TOOL_TYPE_FUNCTION = "function"
TOOL_FUNCTION = "function"
FUNCTION_NAME = "name"
FUNCTION_DESCRIPTION = "description"
FUNCTION_PARAMETERS = "parameters"


@dataclass(frozen=True)
class ToolContext:
    """What a tool handler is allowed to touch: repositories (read-only here) and the
    conversation's project scope. Project-chat tools must be scoped by `project_uuid`.
    """

    uow: UnitOfWork
    project_uuid: UUID | None = None


# A handler takes a validated input model + context and returns the tool result payload.
ToolHandler = Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler

    def to_openai_tool(self) -> dict[str, Any]:
        """Render this tool as an OpenAI Chat Completions tools[] entry."""
        return {
            TOOL_TYPE: TOOL_TYPE_FUNCTION,
            TOOL_FUNCTION: {
                FUNCTION_NAME: self.name,
                FUNCTION_DESCRIPTION: self.description,
                FUNCTION_PARAMETERS: self.input_model.model_json_schema(),
            },
        }
