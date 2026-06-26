"""Capture EKT ground truth + variable corrections from the Gate B review.

At Gate B the Kalkulator accepts or overrides every proposed variable value. This service turns that
review into two records: one VariableCorrection per overridden leaf (the model's proposal vs. the
chosen value, with an optional reason), always; and, when the run is marked as ground truth, one
upserted GroundTruth row holding the endorsed value for every leaf plus the confirmed recipe.

The proposals come from the paused graph state (the pre-resume `vorschlaege`); the build helpers are
pure so they can be unit-tested without a database.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.conversation import Conversation
from shared.models.ground_truth import (
    GoldVariable,
    NewGroundTruth,
    NewVariableCorrection,
)
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.variable_corrections import VariableCorrectionRepository

# AufloesungsMethode value stamped on an overridden value (matches the engine's quelle space).
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
    """One correction per overridden leaf: the proposal (value + provenance + confidence) vs. the
    Kalkulator's value, with the optional reason tag."""
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
    """The endorsed value for every reviewed leaf: the override where one was made, else the
    proposal. An overridden leaf is tagged hitl and flagged so the grader can split model accuracy
    from expert adjustments."""
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


class GroundTruthService:
    def __init__(self, conn: AsyncConnection) -> None:
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
