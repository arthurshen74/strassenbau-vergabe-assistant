from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.conversation import NewConversation
from shared.models.enums import MessageKind, PromptType
from shared.models.message import NewMessage
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository


async def test_conversation_round_trip_and_list(conn: AsyncConnection) -> None:
    repo = ConversationRepository(conn)
    user = uuid4()
    created = await repo.add(
        NewConversation(user_uuid=user, prompt_type=PromptType.DISPATCHER, title="t")
    )
    assert created.prompt_type is PromptType.DISPATCHER
    assert created.project_uuid is None

    fetched = await repo.get(created.conversation_uuid)
    assert fetched is not None and fetched.conversation_uuid == created.conversation_uuid

    listed = await repo.list_by_user(user)
    assert [c.conversation_uuid for c in listed] == [created.conversation_uuid]
    # A different user sees nothing.
    assert await repo.list_by_user(uuid4()) == []


async def test_messages_round_trip_with_jsonb(conn: AsyncConnection) -> None:
    convos = ConversationRepository(conn)
    messages = MessageRepository(conn)
    convo = await convos.add(
        NewConversation(user_uuid=uuid4(), prompt_type=PromptType.DISPATCHER)
    )
    cid = convo.conversation_uuid

    await messages.add(NewMessage(conversation_uuid=cid, kind=MessageKind.USER, content="hi"))
    await messages.add(
        NewMessage(
            conversation_uuid=cid,
            kind=MessageKind.FUNCTION_CALL,
            call_id="c1",
            tool_name="view_projects",
            arguments={"parent_oz": None},
        )
    )
    await messages.add(
        NewMessage(
            conversation_uuid=cid,
            kind=MessageKind.FUNCTION_CALL_OUTPUT,
            call_id="c1",
            tool_name="view_projects",
            success=True,
            data={"projects": []},
        )
    )

    rows = await messages.list_for_conversation(cid)
    assert [m.kind for m in rows] == [
        MessageKind.USER,
        MessageKind.FUNCTION_CALL,
        MessageKind.FUNCTION_CALL_OUTPUT,
    ]
    assert rows[1].arguments == {"parent_oz": None}
    assert rows[2].success is True and rows[2].data == {"projects": []}
