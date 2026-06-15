"""EKT calculator run endpoints: create a run for an LV position, stream it, resume across HITL pauses.

The flow is conversation-first: `create` makes the `ekt_calculator` conversation (owned by the
principal, so it shows in the project conversation list) and returns it; the UI redirects to that
conversation and opens `stream`, which runs the graph in this API request and streams SSE until the
first HITL interrupt or completion. `resume` continues a paused run from its Postgres checkpoint with
the Kalkulator's structured decision. After the run completes, follow-up questions go through the
normal `/conversations/{uuid}/turn` endpoint (project chat)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import (
    Principal,
    get_calculator_run_service,
    get_current_user,
    get_engine,
)
from api.sse import SSE_MEDIA_TYPE, format_sse
from shared.models.conversation import Conversation, NewConversation
from shared.models.conversation_schema import ConversationRead
from shared.models.enums import CalculationStatus, PromptType
from shared.models.sse_schema import (
    DATA,
    DATA_CONTENT,
    DATA_LEVEL,
    EVENT,
    EVENT_DONE,
    EVENT_UI_NOTICE,
    NOTICE_PROCESSING_ERROR,
    NoticeLevel,
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.lv_items import LVItemRepository
from shared.services.calculator.run_service import CalculatorRunService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calculations"])

# Length of the LV Kurztext kept in the conversation title.
TITLE_KURZTEXT_LEN = 60


class CalculationResume(BaseModel):
    """The Kalkulator's structured decision for the current interrupt. Exactly the fields the
    paused stage consumes: work_type (classification), drivers (driver confirmation), action
    (EKT review). Empty `drivers` means accept the assumed values as-is."""

    model_config = ConfigDict(extra="forbid")

    work_type: str | None = None
    drivers: dict[str, Any] | None = None
    action: str | None = None


@router.post(
    "/projects/{project_uuid}/lv-items/{oz}/calculations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_calculation(
    project_uuid: UUID,
    oz: str,
    principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> ConversationRead:
    """Create the ekt_calculator conversation for an LV position. The UI redirects to it and opens
    the stream; the run is addressable by conversation_uuid alone via the stored lv_item_uuid."""
    async with engine.connect() as conn:
        item = await LVItemRepository(conn).get_by_project_and_oz(project_uuid, oz)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no LV position {oz} in project {project_uuid}",
        )
    async with engine.begin() as conn:
        conversation = await ConversationRepository(conn).add(
            NewConversation(
                user_uuid=principal.user_id,
                prompt_type=PromptType.EKT_CALCULATOR,
                project_uuid=project_uuid,
                lv_item_uuid=item.lv_item_uuid,
                calculation_status=CalculationStatus.RUNNING,
                title=f"EKT {oz}: {item.kurztext[:TITLE_KURZTEXT_LEN]}",
            )
        )
    return ConversationRead.model_validate(conversation.model_dump())


@router.post("/conversations/{conversation_uuid}/calculation/stream")
async def stream_calculation(
    conversation_uuid: UUID,
    principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
    service: CalculatorRunService = Depends(get_calculator_run_service),
) -> StreamingResponse:
    """Run the calculation graph and stream it until the first HITL interrupt or completion."""
    async with engine.connect() as conn:
        conversation = await ConversationRepository(conn).get(conversation_uuid)
        item = (
            await LVItemRepository(conn).get(conversation.lv_item_uuid)
            if conversation is not None and conversation.lv_item_uuid is not None
            else None
        )
    _require_calculation(conversation, principal)
    if conversation.calculation_status == CalculationStatus.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="calculation already complete"
        )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="calculation has no LV position"
        )
    events = service.start(conversation, item)
    return StreamingResponse(
        _event_stream(events, conversation_uuid), media_type=SSE_MEDIA_TYPE
    )


@router.post("/conversations/{conversation_uuid}/calculation/resume")
async def resume_calculation(
    conversation_uuid: UUID,
    payload: CalculationResume,
    principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
    service: CalculatorRunService = Depends(get_calculator_run_service),
) -> StreamingResponse:
    """Resume a paused run from its checkpoint with the Kalkulator's decision."""
    async with engine.connect() as conn:
        conversation = await ConversationRepository(conn).get(conversation_uuid)
    _require_calculation(conversation, principal)
    if conversation.calculation_status != CalculationStatus.AWAITING_INPUT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="calculation is not awaiting input"
        )
    decision = payload.model_dump(exclude_none=True)
    events = service.resume(conversation, decision)
    return StreamingResponse(
        _event_stream(events, conversation_uuid), media_type=SSE_MEDIA_TYPE
    )


def _require_calculation(conversation: Conversation | None, principal: Principal) -> None:
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    if conversation.prompt_type != PromptType.EKT_CALCULATOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="conversation is not a calculation"
        )


async def _event_stream(
    events: AsyncIterator[dict[str, Any]], conversation_uuid: UUID
) -> AsyncIterator[str]:
    # The 200 + headers are already committed once streaming starts, so an exception here cannot
    # become an HTTP error; surface it as a ui_notice + done instead and log the cause server-side.
    try:
        async for event in events:
            yield format_sse(event)
    except Exception:
        logger.exception("calculation stream failed conversation=%s", conversation_uuid)
        yield format_sse(
            {
                EVENT: EVENT_UI_NOTICE,
                DATA: {DATA_CONTENT: NOTICE_PROCESSING_ERROR, DATA_LEVEL: NoticeLevel.ERROR},
            }
        )
        yield format_sse({EVENT: EVENT_DONE, DATA: {}})
