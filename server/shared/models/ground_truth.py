"""Domain models for EKT ground-truth capture.

GroundTruth is the expert-confirmed answer for one LV position (the curated gold set); a
VariableCorrection is one Gate B override (proposal vs. the Kalkulator's value), the
append-only telemetry that explains why a value changed. Both are written at Gate B; see
shared.services.ground_truth.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import VariableCorrectionReason


class GoldVariable(BaseModel):
    """The endorsed value for one reviewed leaf, with the provenance that produced
    it."""

    model_config = ConfigDict(extra="forbid")

    wert: str | None = None
    einheit: str | None = None
    art: str | None = None  # BlattArt value: eingabe | satz | stammdaten
    quelle: str | None = None  # AufloesungsMethode value, or hitl when overridden
    overridden: bool = False  # True when the Kalkulator changed the proposal


class NewGroundTruth(BaseModel):
    """Create/upsert model for one position's gold record. PK and timestamps assigned by
    the DB."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    lv_item_uuid: UUID
    source_conversation_uuid: UUID | None = None
    oz: str | None = None
    leistung_key: str
    bauverfahren_key: str | None = None
    gold_variables: dict[str, GoldVariable]
    created_by_user_id: UUID


class GroundTruth(NewGroundTruth):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ground_truth_uuid: UUID
    created_at: datetime
    updated_at: datetime


class GroundTruthUpsert(BaseModel):
    """PUT body for curating one position's gold record. Scope and audit fields come
    from the route (path + principal); oz comes from the LV item, never the client."""

    model_config = ConfigDict(extra="forbid")

    leistung_key: str
    bauverfahren_key: str | None = None
    gold_variables: dict[str, GoldVariable]


class GroundTruthRead(GroundTruth):
    """Gold row plus its drift against the current recipe worklist (see
    shared.services.ground_truth.assess_staleness)."""

    stale: bool = False
    recipe_missing: bool = False  # leistung/bauverfahren no longer in the catalog
    missing_variables: list[str] = []  # in the current worklist but not in gold
    extra_variables: list[str] = []  # in gold but no longer in the worklist


class NewVariableCorrection(BaseModel):
    """Create model for one Gate B override. PK and created_at assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    lv_item_uuid: UUID | None = None
    oz: str | None = None
    conversation_uuid: UUID | None = None
    leistung_key: str | None = None
    bauverfahren_key: str | None = None
    variable_name: str
    proposed_wert: str | None = None
    proposed_quelle: str | None = None
    proposed_konfidenz: str | None = None
    proposed_beleg: str | None = None
    final_wert: str
    reason: VariableCorrectionReason | None = None
    note: str | None = None
    created_by_user_id: UUID


class VariableCorrection(NewVariableCorrection):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    correction_uuid: UUID
    created_at: datetime


class CorrectionSummaryRow(BaseModel):
    """One (variable, reason) group of the error-analysis rollup."""

    model_config = ConfigDict(extra="forbid")

    variable_name: str
    reason: VariableCorrectionReason | None = None
    count: int
