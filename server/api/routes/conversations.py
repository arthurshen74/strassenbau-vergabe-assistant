from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import (
    Principal,
    get_connection,
    get_current_user,
    get_dispatcher,
    get_uow,
)
from api.sse import format_sse
from shared.db.unit_of_work import UnitOfWork
from shared.models.conversation import NewConversation
from shared.models.conversation_schema import ConversationCreate, ConversationRead
from shared.models.message_schema import MessageRead
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository
from shared.services.dispatcher import Dispatcher

router = APIRouter(prefix="/conversations", tags=["conversations"])

SSE_MEDIA_TYPE = "text/event-stream"


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


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
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> StreamingResponse:
    conversation = await ConversationRepository(conn).get(conversation_uuid)
    if conversation is None or conversation.user_uuid != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    async def event_stream() -> AsyncIterator[str]:
        async for event in dispatcher.run_turn(conversation, payload.content):
            yield format_sse(event)

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)
