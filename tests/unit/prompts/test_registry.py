from __future__ import annotations

import pytest
from pydantic import BaseModel

from shared.prompts import registry
from shared.prompts.registry import (
    UnknownOutputSchemaError,
    register_output_schema,
    resolve_output_schema,
)


class SampleOut(BaseModel):
    value: str


class OtherOut(BaseModel):
    other: int


def setup_function() -> None:
    registry.OUTPUT_SCHEMAS.clear()


def test_resolve_none_returns_none() -> None:
    assert resolve_output_schema(None) is None


def test_register_and_resolve() -> None:
    register_output_schema("SampleOut", SampleOut)
    assert resolve_output_schema("SampleOut") is SampleOut


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownOutputSchemaError):
        resolve_output_schema("Nope")


def test_re_register_same_class_is_idempotent() -> None:
    register_output_schema("SampleOut", SampleOut)
    register_output_schema("SampleOut", SampleOut)
    assert resolve_output_schema("SampleOut") is SampleOut


def test_re_register_different_class_raises() -> None:
    register_output_schema("SampleOut", SampleOut)
    with pytest.raises(ValueError):
        register_output_schema("SampleOut", OtherOut)
