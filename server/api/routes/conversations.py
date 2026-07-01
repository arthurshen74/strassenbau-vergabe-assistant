from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import (
    Principal,
    get_calculator_run_service,
    get_connection,
    get_current_user,
    get_llm_client,
    get_project_chat_service,
    get_uow,
)
from api.sse import SSE_MEDIA_TYPE, format_sse
from shared.clients.llm.client import LLMClient
from shared.db.unit_of_work import UnitOfWork
from shared.models.conversation import Conversation, NewConversation
from shared.models.conversation_schema import (
    ConversationCostRead,
    ConversationCreate,
    ConversationRead,
)
from shared.models.enums import CalculationStatus, PromptType, VariableCorrectionReason
from shared.models.lv_item import LVItem
from shared.models.message_schema import MessageRead
from shared.models.retrieval_request_schema import TurnRetrievalConfig
from shared.models.sse_schema import (
    DATA,
    DATA_CONTENT,
    DATA_LEVEL,
    DATA_NAME,
    EVENT,
    EVENT_DONE,
    EVENT_FUNCTION_CALL,
    EVENT_UI_NOTICE,
    NOTICE_PROCESSING_ERROR,
    NoticeLevel,
)
from shared.repositories.conversations import ConversationRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.messages import MessageRepository
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.services.calculator.run_service import CalculatorRunService
from shared.services.conversation_naming import ConversationNamingService
from shared.services.project_chat import ProjectChatService, config_from_request
from shared.services.project_chat_agent import TOOL_CALCULATE_EKT
from shared.services.prompt_runner import PromptRunner
from shared.services.security import InputRejectedError, guard_user_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CalculationResume(BaseModel):
    """The Kalkulator's structured decision for the current HITL gate of a paused calculation.
    project_context_review (pre-Gate-A) `projekt_kontext` maps a changed project global -> its new
    value (locations as address strings, strip dims/Fräsgut as numbers; only changed fields sent);
    method_review (Gate A) confirms the Leistung, selects the Bauverfahren + resources, and
    `lieferanten` maps a baustoff_code -> the chosen Lieferant; variable_review (Gate B) `overrides`
    maps a variable name -> its corrected value (changed leaves only; an empty/absent map accepts
    every proposal as-is). At Gate B, `reasons` optionally tags each override with why it changed,
    and `mark_as_ground_truth` saves the reviewed state as eval ground truth (see
    shared.services.ground_truth)."""

    model_config = ConfigDict(extra="forbid")

    projekt_kontext: dict[str, str] | None = None  # pre-Gate-A: changed project globals -> new value
    leistung_key: str | None = None
    bauverfahren_key: str | None = None
    maschinen: dict[str, str] | None = None        # Ausführungsart slot code -> Maschine code
    baustoff_code: str | None = None
    lieferanten: dict[str, str] | None = None      # Gate A: baustoff_code -> chosen Lieferant code
    overrides: dict[str, Any] | None = None
    reasons: dict[str, VariableCorrectionReason] | None = None  # Gate B: variable name -> why it changed
    mark_as_ground_truth: bool | None = None       # Gate B: persist the reviewed state as ground truth
    cancel: bool | None = None


class TurnRequest(BaseModel):
    """One turn of a chat conversation. Exactly one of `content` (a free-text message, which for a
    position chat may ask to run the calculation) or `resume` (a structured decision answering a
    paused calculation's HITL gate)."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1)
    resume: CalculationResume | None = None
    retrieval: TurnRetrievalConfig | None = None

    @model_validator(mode="after")
    def _exactly_one_input(self) -> TurnRequest:
        if (self.content is None) == (self.resume is None):
            raise ValueError("provide exactly one of `content` or `resume`")
        return self


def get_conversation_naming_service(
    uow: UnitOfWork = Depends(get_uow),
    llm: LLMClient = Depends(get_llm_client),
) -> ConversationNamingService:
    runner = PromptRunner(uow.prompt_versions, llm)
    return ConversationNamingService(runner, uow.conversations, uow.messages)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    principal: Principal = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> ConversationRead:
    created = await uow.conversations.add(
        NewConversation(user_uuid=principal.user_id, **payload.model_dump())
    )
    return ConversationRead.model_validate(created)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    principal: Principal = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_connection),
) -> list[ConversationRead]:
    convos = await ConversationRepository(conn).list_by_user(principal.user_id)
    return [ConversationRead.model_validate(c) for c in convos]


@router.delete("/{conversation_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_uuid: UUID,
    principal: Principal = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> None:
    conversation = await uow.conversations.get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    await uow.conversations.delete(conversation_uuid)


@router.get("/{conversation_uuid}/cost", response_model=ConversationCostRead)
async def get_conversation_cost(
    conversation_uuid: UUID,
    principal: Principal = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_connection),
) -> ConversationCostRead:
    conversation = await ConversationRepository(conn).get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    cost = await OpenRouterUsageRepository(conn).sum_cost_by_conversation(conversation_uuid)
    return ConversationCostRead(conversation_uuid=conversation_uuid, cost=cost)


@router.get("/{conversation_uuid}/messages", response_model=list[MessageRead])
async def list_messages(
    conversation_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[MessageRead]:
    msgs = await MessageRepository(conn).list_for_conversation(conversation_uuid)
    return [MessageRead.model_validate(m) for m in msgs]


@router.post("/{conversation_uuid}/turn")
async def run_turn(
    conversation_uuid: UUID,
    payload: TurnRequest,
    principal: Principal = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_connection),
    project_chat: ProjectChatService = Depends(get_project_chat_service),
    calc: CalculatorRunService = Depends(get_calculator_run_service),
) -> StreamingResponse:
    """One streaming turn. `content` is a free-text message (project chat, or position chat that may
    ask to run the calculation); `resume` is a structured decision answering a paused calculation's
    HITL gate. A position-chat message that trips calculate_ekt streams the calculation in the SAME
    response, until its first gate or completion."""
    conversation = await ConversationRepository(conn).get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    if conversation.prompt_type not in (PromptType.PROJECT_CHAT, PromptType.EKT_CALCULATOR):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation is not continuable as a chat",
        )

    config = config_from_request(payload.retrieval)
    if payload.resume is not None:
        events = _resume_events(calc, conversation, payload.resume)
    else:
        assert payload.content is not None  # the schema validator guarantees one of the two
        events = await _content_events(conn, project_chat, calc, conversation, payload.content, config)

    async def event_stream() -> AsyncIterator[str]:
        # The 200 + headers are already committed once streaming starts, so an exception here
        # cannot become an HTTP error. Surface it as a ui_notice + done instead of letting the
        # connection close silently, and log the cause server-side.
        try:
            async for event in events:
                yield format_sse(event)
        except Exception:
            logger.exception("chat turn stream failed conversation=%s", conversation_uuid)
            yield format_sse(
                {
                    EVENT: EVENT_UI_NOTICE,
                    DATA: {DATA_CONTENT: NOTICE_PROCESSING_ERROR, DATA_LEVEL: NoticeLevel.ERROR},
                }
            )
            yield format_sse({EVENT: EVENT_DONE, DATA: {}})

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)


def _resume_events(
    calc: CalculatorRunService, conversation: Conversation, resume: CalculationResume
) -> AsyncIterator[dict[str, Any]]:
    """Validate and drive a paused calculation's resume; raises before streaming starts."""
    if conversation.prompt_type != PromptType.EKT_CALCULATOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="resume is only valid for a calculation"
        )
    if conversation.calculation_status != CalculationStatus.AWAITING_INPUT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="calculation is not awaiting input"
        )
    return calc.resume(conversation, resume.model_dump(mode="json", exclude_none=True))


async def _content_events(
    conn: AsyncConnection,
    project_chat: ProjectChatService,
    calc: CalculatorRunService,
    conversation: Conversation,
    content: str,
    config: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Validate and build the event stream for a free-text turn; raises before streaming starts."""
    try:
        guard_user_input(content)
    except InputRejectedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if conversation.prompt_type != PromptType.EKT_CALCULATOR:
        return project_chat.run_turn(conversation, content, config)

    # Position chat: a free-text turn is valid while no calculation is running (before it starts,
    # or for Q&A after it completes). Mid-run it must be resumed, not chatted.
    if conversation.calculation_status not in (
        CalculationStatus.AWAITING_START,
        CalculationStatus.COMPLETE,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="calculation is mid-run; resume it instead of chatting",
        )
    item = (
        await LVItemRepository(conn).get(conversation.lv_item_uuid)
        if conversation.lv_item_uuid is not None
        else None
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="conversation has no LV position"
        )
    return _position_chat_then_maybe_calc(project_chat, calc, conversation, item, content, config)


async def _position_chat_then_maybe_calc(
    project_chat: ProjectChatService,
    calc: CalculatorRunService,
    conversation: Conversation,
    item: LVItem,
    content: str,
    config: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Stream the position-chat turn; if the agent trips calculate_ekt, continue into the
    calculation in the same response (until its first HITL gate or completion). calculate_ekt is a
    control signal: it is neither persisted nor shown, only used here to chain the run."""
    kicked = False
    async for event in project_chat.run_turn(
        conversation, content, config, position_context=_position_context(item)
    ):
        if event[EVENT] == EVENT_DONE:
            continue  # defer the terminal done until any chained calculation finishes
        if event[EVENT] == EVENT_FUNCTION_CALL and event[DATA].get(DATA_NAME) == TOOL_CALCULATE_EKT:
            kicked = True
            continue
        yield event
    if kicked:
        async for event in calc.start(conversation, item):
            if event[EVENT] == EVENT_DONE:
                continue
            yield event
    yield {EVENT: EVENT_DONE, DATA: {}}


def _position_context(item: LVItem) -> str:
    """The bound LV position rendered for the position-chat system prompt."""
    lines = [f"Position {item.oz}: {item.kurztext}", f"Menge: {item.menge} {item.einheit}"]
    langtext = item.langtext_resolved or item.langtext
    if langtext:
        lines.append(langtext)
    return "\n".join(lines)


@router.post("/{conversation_uuid}/name", response_model=ConversationRead)
async def name_conversation(
    conversation_uuid: UUID,
    principal: Principal = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
    service: ConversationNamingService = Depends(get_conversation_naming_service),
) -> ConversationRead:
    conversation = await uow.conversations.get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    updated = await service.name_from_first_message(conversation_uuid)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="conversation has no user message to name",
        )
    return ConversationRead.model_validate(updated)
