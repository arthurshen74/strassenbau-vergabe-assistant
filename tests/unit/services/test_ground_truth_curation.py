"""The pure curation helpers of the ground-truth service: worklist derivation for a recipe,
staleness assessment of a gold row against it, and the upsert boundary validation. All run
against the static seed catalog (no DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from shared.models.ground_truth import GoldVariable, GroundTruth
from shared.services.ground_truth import (
    assess_staleness,
    recipe_worklist_names,
    validate_gold_recipe,
)
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.leistung_bauverfahren import kandidaten
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.store import GEOM

LK = "L_FRAESEN"


def _gold(leistung_key: str, bauverfahren_key: str | None, names: list[str]) -> GroundTruth:
    now = datetime.now(timezone.utc)
    return GroundTruth(
        ground_truth_uuid=uuid4(),
        project_uuid=uuid4(),
        lv_item_uuid=uuid4(),
        oz="01.02.0030",
        leistung_key=leistung_key,
        bauverfahren_key=bauverfahren_key,
        gold_variables={n: GoldVariable(wert="1") for n in names},
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_worklist_names_for_valid_recipe_excludes_geometry() -> None:
    bv = kandidaten(LK)[0]
    names = recipe_worklist_names(LK, bv)
    assert names
    geom = GEOM[LEISTUNGEN[LK].einheit]
    assert geom not in names


def test_worklist_names_none_bauverfahren_uses_default_candidate() -> None:
    assert recipe_worklist_names(LK, None) == recipe_worklist_names(LK, kandidaten(LK)[0])


def test_worklist_names_gone_recipe_is_none() -> None:
    assert recipe_worklist_names("l_gibt_es_nicht", None) is None
    not_a_candidate = next(b for b in BAUVERFAHREN if b not in kandidaten(LK))
    assert recipe_worklist_names(LK, not_a_candidate) is None


def test_assess_complete_gold_is_not_stale() -> None:
    names = recipe_worklist_names(LK, None)
    assert names is not None
    read = assess_staleness(_gold(LK, None, names))
    assert read.stale is False
    assert read.recipe_missing is False
    assert read.missing_variables == []
    assert read.extra_variables == []


def test_assess_reports_missing_and_extra_names() -> None:
    names = recipe_worklist_names(LK, None)
    assert names is not None and len(names) > 1
    dropped = names[0]
    read = assess_staleness(_gold(LK, None, [*names[1:], "erfundene_variable"]))
    assert read.stale is True
    assert dropped in read.missing_variables
    assert read.extra_variables == ["erfundene_variable"]


def test_assess_gone_recipe_is_recipe_missing() -> None:
    read = assess_staleness(_gold("l_gibt_es_nicht", None, ["tiefe_cm"]))
    assert read.stale is True
    assert read.recipe_missing is True
    assert read.extra_variables == ["tiefe_cm"]


def test_validate_accepts_worklist_subset() -> None:
    names = recipe_worklist_names(LK, None)
    assert names is not None
    assert validate_gold_recipe(LK, None, names[:1]) == []


def test_validate_rejects_unknown_leistung_bv_and_variable() -> None:
    assert validate_gold_recipe("l_gibt_es_nicht", None, []) != []

    not_a_candidate = next(b for b in BAUVERFAHREN if b not in kandidaten(LK))
    assert validate_gold_recipe(LK, not_a_candidate, []) != []

    problems = validate_gold_recipe(LK, None, ["erfundene_variable"])
    assert problems and "erfundene_variable" in problems[0]
