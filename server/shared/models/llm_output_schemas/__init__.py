"""Pydantic output schemas for JSON-schema-constrained LLM calls.

One module per feature/prompt; each class is the validated shape an LLM response must take.
`registry` wires these to their `PromptType`; `PromptRunner` resolves the schema and the LLM
transport validates responses against it at the boundary.
"""

from __future__ import annotations

from shared.models.llm_output_schemas.lv_extraction import (
    LVExtraction,
    LVPosition,
)
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite
from shared.models.llm_output_schemas.project_chat_route import (
    ProjectChatAction,
    ProjectChatRoute,
)
from shared.models.llm_output_schemas.registry import (
    PROMPT_OUTPUT_MODELS,
    output_model_for,
)

__all__ = [
    "PROMPT_OUTPUT_MODELS",
    "LVExtraction",
    "LVPosition",
    "MultiQueryRewrite",
    "ProjectChatAction",
    "ProjectChatRoute",
    "output_model_for",
]
