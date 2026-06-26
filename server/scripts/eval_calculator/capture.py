"""Re-run one position's extraction headlessly to its Gate B proposals.

Drives launch -> ... -> Gate A, records the system's own classification, then resumes Gate A with the
GOLD recipe so the worklist is the right one, and stops at Gate B holding the system's fresh
proposals (`vorschlaege`). The price compute is never run -- only the extraction is evaluated.
Pinning the gold recipe decouples extraction quality from classification, which is scored separately.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.types import Command

from shared.services.calculator.state import STAGE_METHOD_REVIEW


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
    """Return (system_leistung_key, proposals). proposals is the Gate B `vorschlaege` keyed by
    variable name; empty if the run never reached Gate B (e.g. the gold Leistung has no worklist)."""
    cfg = {"configurable": {"thread_id": thread_id}}
    payload = {
        "position": position,
        "project_uuid": project_uuid,
        "vorgaben": {},
        "chat_verlauf": [],
    }
    gate_a = await _drive_to_interrupt(app, cfg, payload)
    if gate_a is None or gate_a.get("stage") != STAGE_METHOD_REVIEW:
        # Never reached Gate A (cancelled / degenerate): no classification, no proposals.
        return None, {}
    system_leistung_key = gate_a.get("leistung_key")
    await _drive_to_interrupt(
        app,
        cfg,
        Command(resume={"leistung_key": gold_leistung_key, "bauverfahren_key": gold_bauverfahren_key}),
    )
    proposals = (await app.aget_state(cfg)).values.get("vorschlaege") or {}
    return system_leistung_key, proposals
