"""Wiring of each PromptType to an optional Pydantic output model (schema-in-code).

The single place that declares which prompt types are answered with JSON-schema-constrained
structured output and which are free-form. A PromptType absent from the map has no output
schema: the call returns raw text. The schema classes live in sibling modules; this only wires
them. `PromptRunner` resolves the model for a prompt type at call time.

Output models must stay within the JSON-Schema subset Anthropic's structured outputs support:
no numeric (`minimum`/`maximum`) or length (`minLength`) constraints, no recursion, no `$ref`;
`additionalProperties: false` (via `ConfigDict(extra="forbid")`) is required for strict mode.
"""

from __future__ import annotations

from pydantic import BaseModel

from shared.models.enums import PromptType
from shared.models.llm_output_schemas.lv_extraction import LVExtraction
from shared.models.llm_output_schemas.lv_membership import LVMembership
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite

PROMPT_OUTPUT_MODELS: dict[PromptType, type[BaseModel]] = {
    PromptType.MULTI_QUESTION_GENERATOR: MultiQueryRewrite,
    PromptType.AGGREGATE_LV_MEMBERSHIP: LVMembership,
    PromptType.LV_EXTRACTION: LVExtraction,
}


def output_model_for(prompt_type: PromptType) -> type[BaseModel] | None:
    """Return the Pydantic output model for a prompt type, or None when the call is free-form."""
    return PROMPT_OUTPUT_MODELS.get(prompt_type)
