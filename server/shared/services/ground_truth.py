"""Capture and curate EKT ground truth + variable corrections.

Capture (Gate B): the Kalkulator accepts or overrides every proposed variable value.
This service turns that review into two records: one VariableCorrection per overridden
leaf (the model's proposal vs. the chosen value, with an optional reason), always; and,
when the run is marked as ground truth, one upserted GroundTruth row holding the
endorsed value for every leaf plus the confirmed recipe.

Curation (eval UI): list gold with staleness against the current recipe worklist, upsert
edited gold (validated against the catalog + worklist), delete, and read corrections
(filtered list + error-analysis summary). Corrections have no write path here beyond
Gate B — they are telemetry.

The proposals come from the paused graph state (the pre-resume `vorschlaege`); the
build/assess helpers are pure so they can be unit-tested without a database.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.conversation import Conversation
from shared.models.enums import VariableCorrectionReason
from shared.models.ground_truth import (
    CorrectionSummaryRow,
    GoldVariable,
    GroundTruth,
    GroundTruthRead,
    GroundTruthUpsert,
    NewGroundTruth,
    NewVariableCorrection,
    VariableCorrection,
)
from shared.repositories.documents import DocumentRepository
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.variable_corrections import VariableCorrectionRepository
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.leistung_bauverfahren import kandidaten
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.model import Kalkulator
from shared.services.kalkulation_v2.store import FORMELN, GEOM, KATALOG
from shared.services.kalkulation_v2.worklist import benoetigte_variablen

# AufloesungsMethode value stamped on an overridden value (matches the engine's quelle
# space).
QUELLE_OVERRIDE = "hitl"


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def build_corrections(
    *,
    conversation: Conversation,
    oz: str | None,
    leistung_key: str | None,
    bauverfahren_key: str | None,
    proposals: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
    reasons: dict[str, Any],
) -> list[NewVariableCorrection]:
    """One correction per overridden leaf: the proposal (value + provenance +
    confidence) vs. the Kalkulator's value, with the optional reason tag."""
    corrections: list[NewVariableCorrection] = []
    for name, final in overrides.items():
        prop = proposals.get(name) or {}
        corrections.append(
            NewVariableCorrection(
                project_uuid=conversation.project_uuid,
                lv_item_uuid=conversation.lv_item_uuid,
                oz=oz,
                conversation_uuid=conversation.conversation_uuid,
                leistung_key=leistung_key,
                bauverfahren_key=bauverfahren_key,
                variable_name=name,
                proposed_wert=_opt_str(prop.get("wert")),
                proposed_quelle=_opt_str(prop.get("quelle")),
                proposed_konfidenz=_opt_str(prop.get("konfidenz")),
                proposed_beleg=_opt_str(prop.get("beleg")),
                final_wert=str(final),
                reason=reasons.get(name),
                created_by_user_id=conversation.user_uuid,
            )
        )
    return corrections


def build_gold_variables(
    proposals: dict[str, dict[str, Any]], overrides: dict[str, Any]
) -> dict[str, GoldVariable]:
    """The endorsed value for every reviewed leaf: the override where one was made, else
    the proposal. An overridden leaf is tagged hitl and flagged so the grader can split
    model accuracy from expert adjustments."""
    gold: dict[str, GoldVariable] = {}
    for name, prop in proposals.items():
        overridden = name in overrides
        wert = overrides[name] if overridden else prop.get("wert")
        gold[name] = GoldVariable(
            wert=_opt_str(wert),
            einheit=_opt_str(prop.get("einheit")),
            art=_opt_str(prop.get("art")),
            quelle=QUELLE_OVERRIDE if overridden else _opt_str(prop.get("quelle")),
            overridden=overridden,
        )
    return gold


def recipe_worklist_names(
    leistung_key: str, bauverfahren_key: str | None
) -> list[str] | None:
    """The leaf variable names Gate B reviews for this recipe — the geometry leaf is
    excluded (booked from the LV Menge, mirrors derive_required_variables in the
    calculator graph). None when the catalog can no longer resolve the recipe: unknown
    Leistung, a Bauverfahren that is not (or no longer) a candidate, or a worklist
    referencing a removed variable — all the gold row predating a catalog change."""
    leistung = LEISTUNGEN.get(leistung_key)
    if leistung is None:
        return None
    kand = kandidaten(leistung_key)
    bv_key = (
        bauverfahren_key
        if bauverfahren_key is not None
        else (kand[0] if kand else None)
    )
    if bv_key is None or bv_key not in kand:
        return None
    geom = GEOM.get(leistung.einheit)
    gebucht = frozenset({geom}) if geom else frozenset()
    kalk = Kalkulator(KATALOG, FORMELN)
    try:
        blaetter = benoetigte_variablen(BAUVERFAHREN[bv_key], kalk, gebucht=gebucht)
    except KeyError:
        return None
    return [b.name for b in blaetter]


def assess_staleness(gold: GroundTruth) -> GroundTruthRead:
    """Wrap a gold row with its drift against the current recipe worklist. A gold set
    whose variable names diverge from the worklist grades misleadingly (stale names read
    as missed, new names go un-graded), so any difference flags the row for
    re-confirmation."""
    worklist = recipe_worklist_names(gold.leistung_key, gold.bauverfahren_key)
    if worklist is None:
        return GroundTruthRead(
            **gold.model_dump(),
            stale=True,
            recipe_missing=True,
            extra_variables=sorted(gold.gold_variables),
        )
    names = set(gold.gold_variables)
    missing = [n for n in worklist if n not in names]
    extra = sorted(names.difference(worklist))
    return GroundTruthRead(
        **gold.model_dump(),
        stale=bool(missing or extra),
        missing_variables=missing,
        extra_variables=extra,
    )


def validate_gold_recipe(
    leistung_key: str, bauverfahren_key: str | None, variable_names: Iterable[str]
) -> list[str]:
    """Boundary validation for a curated upsert: the recipe must exist in the catalog
    and every gold variable must be in its worklist (a subset is fine — it just reads as
    stale). Returns human-readable problems; empty means valid."""
    if leistung_key not in LEISTUNGEN:
        return [f"leistung_key {leistung_key!r} ist nicht im Katalog"]
    if bauverfahren_key is not None and bauverfahren_key not in kandidaten(
        leistung_key
    ):
        return [
            f"bauverfahren_key {bauverfahren_key!r} ist kein Kandidat für "
            f"{leistung_key!r}"
        ]
    worklist = recipe_worklist_names(leistung_key, bauverfahren_key)
    unknown = sorted(set(variable_names).difference(worklist or []))
    if unknown:
        return ["nicht in der Rezept-Worklist: " + ", ".join(unknown)]
    return []


class GroundTruthService:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn
        self._ground_truth = GroundTruthRepository(conn)
        self._corrections = VariableCorrectionRepository(conn)

    async def capture_gate_b(
        self,
        *,
        conversation: Conversation,
        oz: str | None,
        leistung_key: str | None,
        bauverfahren_key: str | None,
        proposals: dict[str, dict[str, Any]],
        overrides: dict[str, Any],
        reasons: dict[str, Any],
        mark_as_ground_truth: bool,
    ) -> None:
        await self._corrections.add_many(
            build_corrections(
                conversation=conversation,
                oz=oz,
                leistung_key=leistung_key,
                bauverfahren_key=bauverfahren_key,
                proposals=proposals,
                overrides=overrides,
                reasons=reasons,
            )
        )
        if mark_as_ground_truth and leistung_key:
            await self._ground_truth.upsert(
                NewGroundTruth(
                    project_uuid=conversation.project_uuid,
                    lv_item_uuid=conversation.lv_item_uuid,
                    source_conversation_uuid=conversation.conversation_uuid,
                    oz=oz,
                    leistung_key=leistung_key,
                    bauverfahren_key=bauverfahren_key,
                    gold_variables=build_gold_variables(proposals, overrides),
                    created_by_user_id=conversation.user_uuid,
                )
            )

    async def list_gold(self, project_uuid: UUID) -> list[GroundTruthRead]:
        rows = await self._ground_truth.list_by_project(project_uuid)
        return [assess_staleness(g) for g in rows]

    async def upsert_gold(
        self,
        *,
        project_uuid: UUID,
        lv_item_uuid: UUID,
        payload: GroundTruthUpsert,
        user_id: UUID,
    ) -> GroundTruthRead:
        """Curated create/edit of one position's gold record. Raises LookupError when
        the LV item is not in this project, ValueError when the recipe/variables fail
        catalog validation. Re-saving unchanged content re-stamps updated_at (the "Gold
        neu bestätigen" flow)."""
        item = await LVItemRepository(self._conn).get(lv_item_uuid)
        document = (
            await DocumentRepository(self._conn).get(item.document_uuid)
            if item
            else None
        )
        if item is None or document is None or document.project_uuid != project_uuid:
            raise LookupError("LV position not found in this project")
        problems = validate_gold_recipe(
            payload.leistung_key, payload.bauverfahren_key, payload.gold_variables
        )
        if problems:
            raise ValueError("; ".join(problems))
        existing = await self._ground_truth.get(project_uuid, lv_item_uuid)
        saved = await self._ground_truth.upsert(
            NewGroundTruth(
                project_uuid=project_uuid,
                lv_item_uuid=lv_item_uuid,
                source_conversation_uuid=(
                    existing.source_conversation_uuid if existing else None
                ),
                oz=item.oz,
                leistung_key=payload.leistung_key,
                bauverfahren_key=payload.bauverfahren_key,
                gold_variables=payload.gold_variables,
                created_by_user_id=user_id,
            )
        )
        return assess_staleness(saved)

    async def delete_gold(self, project_uuid: UUID, lv_item_uuid: UUID) -> bool:
        return await self._ground_truth.delete(project_uuid, lv_item_uuid)

    async def list_corrections(
        self,
        project_uuid: UUID,
        *,
        variable_name: str | None = None,
        reason: VariableCorrectionReason | None = None,
    ) -> list[VariableCorrection]:
        return await self._corrections.list_by_project(
            project_uuid, variable_name=variable_name, reason=reason
        )

    async def corrections_summary(
        self, project_uuid: UUID
    ) -> list[CorrectionSummaryRow]:
        return await self._corrections.summary_by_project(project_uuid)
