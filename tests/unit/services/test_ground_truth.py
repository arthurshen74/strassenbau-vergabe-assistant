"""build_corrections / build_gold_variables: the pure Gate B capture logic.

These exercise the diff between the paused proposals and the Kalkulator's overrides without a
database -- one correction per changed leaf (proposal vs. final + reason), and the endorsed gold
value per leaf (the override where made, else the proposal, tagged hitl when overridden)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from shared.models.conversation import Conversation
from shared.models.enums import PromptType, VariableCorrectionReason
from shared.services.ground_truth import (
    QUELLE_OVERRIDE,
    build_corrections,
    build_gold_variables,
)


def _conversation() -> Conversation:
    return Conversation(
        conversation_uuid=uuid4(),
        user_uuid=uuid4(),
        project_uuid=uuid4(),
        prompt_type=PromptType.EKT_CALCULATOR,
        lv_item_uuid=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# Two worklist leaves as the paused state holds them: one read from the Langtext, one unresolved
# (the model found nothing and left it for review).
_PROPOSALS = {
    "fraestiefe": {
        "wert": "4", "einheit": "cm", "art": "eingabe", "quelle": "langtext",
        "konfidenz": "0.91", "beleg": "Fräsen 4 cm",
    },
    "breite": {
        "wert": None, "einheit": "m", "art": "eingabe", "quelle": None,
        "konfidenz": None, "beleg": None,
    },
}


def test_build_corrections_one_per_override() -> None:
    convo = _conversation()

    corrections = build_corrections(
        conversation=convo,
        oz="01.02.0030",
        leistung_key="fraesen",
        bauverfahren_key="bv",
        proposals=_PROPOSALS,
        overrides={"breite": "3.5"},
        reasons={"breite": VariableCorrectionReason.FALSCHE_QUELLE},
    )

    assert len(corrections) == 1                  # only the changed leaf
    c = corrections[0]
    assert c.variable_name == "breite"
    assert c.proposed_wert is None                # the model resolved nothing
    assert c.final_wert == "3.5"
    assert c.reason == VariableCorrectionReason.FALSCHE_QUELLE
    assert c.oz == "01.02.0030"
    assert c.project_uuid == convo.project_uuid
    assert c.lv_item_uuid == convo.lv_item_uuid
    assert c.conversation_uuid == convo.conversation_uuid
    assert c.created_by_user_id == convo.user_uuid


def test_build_corrections_carries_proposal_provenance() -> None:
    convo = _conversation()

    corrections = build_corrections(
        conversation=convo,
        oz=None,
        leistung_key=None,
        bauverfahren_key=None,
        proposals=_PROPOSALS,
        overrides={"fraestiefe": "5"},
        reasons={},
    )

    c = corrections[0]
    assert c.proposed_wert == "4"
    assert c.proposed_quelle == "langtext"
    assert c.proposed_konfidenz == "0.91"
    assert c.proposed_beleg == "Fräsen 4 cm"
    assert c.final_wert == "5"
    assert c.reason is None                        # reason is optional


def test_build_gold_variables_marks_overrides() -> None:
    gold = build_gold_variables(_PROPOSALS, overrides={"breite": "3.5"})

    # Accepted leaf keeps the proposal and its provenance.
    assert gold["fraestiefe"].wert == "4"
    assert gold["fraestiefe"].overridden is False
    assert gold["fraestiefe"].quelle == "langtext"

    # Overridden leaf takes the Kalkulator's value, tagged as a human decision.
    assert gold["breite"].wert == "3.5"
    assert gold["breite"].overridden is True
    assert gold["breite"].quelle == QUELLE_OVERRIDE


def test_build_gold_variables_all_accepted() -> None:
    gold = build_gold_variables(_PROPOSALS, overrides={})

    assert all(not g.overridden for g in gold.values())
    assert gold["fraestiefe"].wert == "4"
    assert gold["breite"].wert is None             # unresolved, accepted as-is
