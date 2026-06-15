from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import (
    Principal,
    get_connection,
    get_current_user,
    get_llm_client,
    get_project_chat_service,
    get_uow,
)
from api.sse import SSE_MEDIA_TYPE, format_sse
from shared.clients.llm.client import LLMClient
from shared.db.unit_of_work import UnitOfWork
from shared.models.conversation import NewConversation
from shared.models.conversation_schema import (
    ConversationCostRead,
    ConversationCreate,
    ConversationRead,
)
from shared.models.enums import CalculationStatus, PromptType
from shared.models.message_schema import MessageRead
from shared.models.retrieval_request_schema import TurnRetrievalConfig
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
from shared.repositories.messages import MessageRepository
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.services.conversation_naming import ConversationNamingService
from shared.services.project_chat import ProjectChatService, config_from_request
from shared.services.prompt_runner import PromptRunner
from shared.services.security import InputRejectedError, guard_user_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    retrieval: TurnRetrievalConfig | None = None


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
) -> StreamingResponse:
    try:
        guard_user_input(payload.content)
    except InputRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    conversation = await ConversationRepository(conn).get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    # Project chats continue here; an ekt_calculator conversation also continues here for follow-up
    # questions, but only once its run has completed -- mid-run it is driven by the calculation
    # resume endpoint, not a free-text turn. The single-shot dispatcher has its own stateless endpoint.
    if conversation.prompt_type not in (PromptType.PROJECT_CHAT, PromptType.EKT_CALCULATOR):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation is not continuable as a chat",
        )
    if (
        conversation.prompt_type == PromptType.EKT_CALCULATOR
        and conversation.calculation_status != CalculationStatus.COMPLETE
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="calculation is not complete; resume the calculation instead of chatting",
        )

    events = project_chat.run_turn(
        conversation, payload.content, config_from_request(payload.retrieval)
    )

    async def event_stream() -> AsyncIterator[str]:
        # The 200 + headers are already committed once streaming starts, so an exception here
        # cannot become an HTTP error. Surface it as a ui_notice + done instead of letting the
        # connection close silently, and log the cause server-side.
        try:
            async for event in events:
                yield format_sse(event)
        except Exception:
            logger.exception("project chat turn stream failed conversation=%s", conversation_uuid)
            yield format_sse(
                {
                    EVENT: EVENT_UI_NOTICE,
                    DATA: {DATA_CONTENT: NOTICE_PROCESSING_ERROR, DATA_LEVEL: NoticeLevel.ERROR},
                }
            )
            yield format_sse({EVENT: EVENT_DONE, DATA: {}})

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)


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
