"""Pattern compilation and spaCy validation for the DB-backed EntityRuler.

Validation compiles against a throwaway blank pipeline, so these tests pay no
model-load cost.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from shared.models.entity_rule import EntityPattern, EntityRule
from shared.services.nlp import entity_ruler as ruler_module
from shared.services.nlp.entity_ruler import (
    compile_pattern_dicts,
    ensure_ruler_current,
    validate_pattern,
)


def _rule(label: str, pattern: EntityPattern, pattern_id: str | None) -> EntityRule:
    now = datetime(2026, 1, 1)
    return EntityRule(
        entity_rule_uuid=uuid4(),
        label=label,
        pattern=pattern,
        pattern_id=pattern_id,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def test_valid_string_pattern_passes() -> None:
    validate_pattern("BAUSTOFF", "Asphaltbeton")


def test_valid_token_list_pattern_passes() -> None:
    validate_pattern("DIN_NORM", [{"ORTH": "DIN"}, {"TEXT": {"REGEX": r"^\d+$"}}])


def test_invalid_token_attribute_rejected_with_message() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_pattern("BAUSTOFF", [{"NOT_A_REAL_ATTR": "x"}])
    assert str(excinfo.value)  # spaCy's own message is surfaced, not empty


def test_compile_includes_id_only_when_present() -> None:
    rules = [
        _rule("BAUSTOFF", "Beton", "baustoff_beton"),
        _rule("EINHEIT", "cm", None),
    ]
    dicts = compile_pattern_dicts(rules)

    assert dicts[0] == {"label": "BAUSTOFF", "pattern": "Beton", "id": "baustoff_beton"}
    assert dicts[1] == {"label": "EINHEIT", "pattern": "cm"}
    assert "id" not in dicts[1]


async def test_clean_ruler_skips_db_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean dirty flag short-circuits before any DB access or pipe rebuild."""
    monkeypatch.setattr(ruler_module, "_dirty", False)
    engine = MagicMock()
    nlp = MagicMock()

    await ensure_ruler_current(nlp, engine)

    engine.begin.assert_not_called()
    nlp.has_pipe.assert_not_called()
    nlp.add_pipe.assert_not_called()
