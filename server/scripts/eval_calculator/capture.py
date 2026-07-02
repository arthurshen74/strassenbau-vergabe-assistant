"""Re-run one position's extraction headlessly to its variable-gate proposals.

Drives launch -> ... -> Gate 2 (Leistung/BV), records the system's own classification, resumes with
the GOLD recipe so the worklist is the right one, accepts the proposed Material at Gate 3 (for a
material recipe), and stops at the variable gate holding the system's fresh proposals
(`vorschlaege`). The price compute is never run -- only the extraction is evaluated. Pinning the gold
recipe decouples extraction quality from classification, which is scored separately.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.types import Command

from shared.services.calculator.state import (
    STAGE_LEISTUNG_BV_REVIEW,
    STAGE_MATERIAL_REVIEW,
)


async def _drive_to_interrupt(app: Any, cfg: dict[str, Any], payload: Any) -> dict[str, Any] | None:
    """Run until the next HITL interrupt or completion; return the interrupt payload, or None."""
    pending: dict[str, Any] | None = None
    async for update in app.astream(payload, cfg, stream_mode="updates"):
        if "__interrupt__" in update:
            pending = update["__interrupt__"][0].value
    return pending


async def capture_extraction(
    *,
    app: Any,
    thread_id: str,
    position: dict[str, Any],
    project_uuid: UUID,
    gold_leistung_key: str,
    gold_bauverfahren_key: str | None,
) -> tuple[str | None, dict[str, dict[str, Any]]]:
    """Return (system_leistung_key, proposals). proposals is the variable-gate `vorschlaege` keyed by
    variable name; empty if the run never reached it (e.g. the gold Leistung has no worklist)."""
    cfg = {"configurable": {"thread_id": thread_id}}
    payload = {
        "position": position,
        "project_uuid": project_uuid,
        "vorgaben": {},
        "chat_verlauf": [],
    }
    gate2 = await _drive_to_interrupt(app, cfg, payload)
    if gate2 is None or gate2.get("stage") != STAGE_LEISTUNG_BV_REVIEW:
        # Never reached Gate 2 (cancelled / degenerate): no classification, no proposals.
        return None, {}
    system_leistung_key = gate2.get("leistung_key")
    nxt = await _drive_to_interrupt(
        app,
        cfg,
        Command(resume={"leistung_key": gold_leistung_key, "bauverfahren_key": gold_bauverfahren_key}),
    )
    # A material recipe pauses at Gate 3 first; accept the BM25 proposal to reach the variable gate.
    if nxt is not None and nxt.get("stage") == STAGE_MATERIAL_REVIEW:
        default = (nxt.get("baustoff_vorschlag") or {}).get("code")
        await _drive_to_interrupt(app, cfg, Command(resume={"baustoff_code": default}))
    proposals = (await app.aget_state(cfg)).values.get("vorschlaege") or {}
    return system_leistung_key, proposals
