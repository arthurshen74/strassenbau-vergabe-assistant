"""Schema-in-code wiring of each PromptType to an optional Pydantic output model.

This is the single place that declares which prompt types are answered with JSON-schema
constrained structured output and which are free-form. A PromptType absent from the map has
no output schema: the call returns raw text with no structured-output enforcement. The schema
classes themselves live in `shared.models.llm_output_schemas`; this module only wires them.
"""

from __future__ import annotations

from pydantic import BaseModel

from shared.models.enums import PromptType
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite

PROMPT_OUTPUT_MODELS: dict[PromptType, type[BaseModel]] = {
    PromptType.MULTI_QUESTION_GENERATOR: MultiQueryRewrite,
}


def output_model_for(prompt_type: PromptType) -> type[BaseModel] | None:
    """Return the Pydantic output model for a prompt type, or None when the call is free-form."""
    return PROMPT_OUTPUT_MODELS.get(prompt_type)
