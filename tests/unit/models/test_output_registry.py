from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from shared.models.enums import PromptType
from shared.models.llm_output_schemas import (
    PROMPT_OUTPUT_MODELS,
    LVExtraction,
    LVMembership,
    MultiQueryRewrite,
    output_model_for,
)


def test_mapped_prompt_type_returns_its_model() -> None:
    assert output_model_for(PromptType.MULTI_QUESTION_GENERATOR) is MultiQueryRewrite
    assert output_model_for(PromptType.AGGREGATE_LV_MEMBERSHIP) is LVMembership
    assert output_model_for(PromptType.LV_EXTRACTION) is LVExtraction


def test_unmapped_prompt_type_returns_none() -> None:
    assert output_model_for(PromptType.DISPATCHER) is None


def test_every_mapped_value_is_a_basemodel_subclass() -> None:
    assert PROMPT_OUTPUT_MODELS
    for model in PROMPT_OUTPUT_MODELS.values():
        assert issubclass(model, BaseModel)


@pytest.mark.parametrize("model", list(PROMPT_OUTPUT_MODELS.values()))
def test_registered_schemas_are_strict_mode_safe(model: type[BaseModel]) -> None:
    """Every registered schema is sent verbatim with strict=True, so it must stay in the
    supported subset: no $ref/$defs, additionalProperties false, and all properties required."""
    schema = model.model_json_schema()
    assert "$ref" not in json.dumps(schema)
    assert "$defs" not in schema
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
