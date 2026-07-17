"""Create a position-chat conversation for an LV position.

The flow is conversation-first: this endpoint makes the `ekt_calculator` conversation
(owned by the principal, so it shows in the project conversation list), bound to the LV
position via `lv_item_uuid`, and seeds the opening message with the position details.
The UI redirects to it and the user chats about the position; asking to run the EKT
calculation trips the agent's `calculate_ekt` tool, which the
`/conversations/{uuid}/turn` endpoint continues into the calculation (streaming
reasoning, pausing at HITL gates, resuming via the same turn endpoint)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import Principal, get_current_user, get_engine
from shared.models.conversation import NewConversation
from shared.models.conversation_schema import ConversationRead
from shared.models.enums import CalculationStatus, MessageKind, PromptType
from shared.models.lv_item import LVItem
from shared.models.message import NewMessage
from shared.repositories.conversations import ConversationRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.messages import MessageRepository

router = APIRouter(tags=["calculations"])

# Length of the LV Kurztext kept in the conversation title.
TITLE_KURZTEXT_LEN = 60


def _lv_details_text(item: LVItem) -> str:
    """The LV position rendered as the position chat's opening assistant message."""
    lines = [
        f"**Position {item.oz}** — {item.kurztext}",
        f"Menge: {item.menge} {item.einheit}",
    ]
    langtext = item.langtext_resolved or item.langtext
    if langtext:
        lines.extend(("", langtext))
    return "\n".join(lines)


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
    """Create the position-chat conversation for an LV position and seed its opening
    message. The UI redirects to it; the user chats about the position and can ask to
    run the EKT calculation, which the turn endpoint continues into the calculation.
    `awaiting_start` here means "position chat, calculation not yet run"."""
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
                calculation_status=CalculationStatus.AWAITING_START,
                title=f"EKT {oz}: {item.kurztext[:TITLE_KURZTEXT_LEN]}",
            )
        )
    async with engine.begin() as conn:
        await MessageRepository(conn).add(
            NewMessage(
                conversation_uuid=conversation.conversation_uuid,
                kind=MessageKind.ASSISTANT,
                content=_lv_details_text(item),
            )
        )
    return ConversationRead.model_validate(conversation.model_dump())
