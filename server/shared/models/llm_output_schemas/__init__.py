"""Pydantic output schemas for JSON-schema-constrained LLM calls.

One module per feature/prompt; each class is the validated shape an LLM response must take.
`clients.llm.prompt_registry` wires these to their `PromptType`; the LLM transport validates
responses against them at the boundary.
"""

from __future__ import annotations

from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite

__all__ = ["MultiQueryRewrite"]
