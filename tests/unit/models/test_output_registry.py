from __future__ import annotations

from pydantic import BaseModel

from shared.models.enums import PromptType
from shared.models.llm_output_schemas import (
    PROMPT_OUTPUT_MODELS,
    MultiQueryRewrite,
    output_model_for,
)


def test_mapped_prompt_type_returns_its_model() -> None:
    assert output_model_for(PromptType.MULTI_QUESTION_GENERATOR) is MultiQueryRewrite


def test_unmapped_prompt_type_returns_none() -> None:
    assert output_model_for(PromptType.DISPATCHER) is None


def test_every_mapped_value_is_a_basemodel_subclass() -> None:
    assert PROMPT_OUTPUT_MODELS
    for model in PROMPT_OUTPUT_MODELS.values():
        assert issubclass(model, BaseModel)
