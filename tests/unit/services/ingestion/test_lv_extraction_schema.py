from __future__ import annotations

import json

from shared.models.llm_output_schemas.lv_extraction import LVExtraction, inline_defs


def test_wire_schema_has_no_ref_or_defs() -> None:
    schema = LVExtraction.model_json_schema()
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)


def test_wire_schema_still_describes_position_objects() -> None:
    schema = LVExtraction.model_json_schema()
    items = schema["properties"]["positions"]["items"]
    assert items["type"] == "object"
    # strict mode requires every property listed as required and additionalProperties false.
    assert items["additionalProperties"] is False
    assert set(items["required"]) == set(items["properties"])
    assert "oz" in items["properties"] and "kurztext_line" in items["properties"]


def test_inline_defs_resolves_refs_and_keeps_siblings() -> None:
    schema = {
        "$defs": {"Child": {"type": "object", "properties": {"x": {"type": "integer"}}}},
        "type": "object",
        "properties": {"child": {"$ref": "#/$defs/Child", "description": "kept"}},
    }
    inlined = inline_defs(schema)
    assert "$defs" not in inlined
    assert inlined["properties"]["child"]["type"] == "object"
    assert inlined["properties"]["child"]["description"] == "kept"
