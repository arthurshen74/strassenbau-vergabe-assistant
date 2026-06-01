"""End-to-end dispatcher loop against real Postgres with a scripted LLM.

The fake LLM scripts two turns: first a tool call (view_projects), then a text answer. We assert
the SSE event sequence and that every turn shape is persisted, then clean up (the conversation
and the seeded prompt commit through the dispatcher's own short transactions)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.events import Done, StreamEvent, TextDelta, ToolCall, ToolCallsReady
from shared.db.tables.conversations import conversations
from shared.db.tables.prompt_versions import prompt_versions
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind, PromptType
from shared.repositories.messages import MessageRepository
from shared.services.dispatcher import (
    DATA,
    EVENT,
    EVENT_DONE,
    EVENT_FUNCTION_CALL,
    EVENT_FUNCTION_CALL_OUTPUT,
    EVENT_TEXT_DELTA,
    Dispatcher,
)


class _FakeLLM:
    """Turn 1 -> one tool call; turn 2 -> text."""

    def __init__(self) -> None:
        self.turns = 0

    async def stream_chat(self, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        self.turns += 1
        if self.turns == 1:
            yield ToolCallsReady(
                tool_calls=[ToolCall(id="c1", name="view_projects", arguments="{}")]
            )
            yield Done(finish_reason="tool_calls")
        else:
            yield TextDelta(content="Here are ")
            yield TextDelta(content="the projects.")
            yield Done(finish_reason="stop")


async def test_dispatcher_tool_then_text(engine: AsyncEngine) -> None:
    user = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            insert(prompt_versions).values(
                prompt_type=PromptType.DISPATCHER.value,
                version=1,
                model_name="x/y",
                system_prompt="route requests",
                temperature=0.0,
            )
        )
        row = (
            await conn.execute(
                insert(conversations)
                .values(user_uuid=user, prompt_type=PromptType.DISPATCHER.value)
                .returning(conversations)
            )
        ).mappings().one()
    conversation = Conversation.model_validate(dict(row))

    dispatcher = Dispatcher(_FakeLLM(), engine)  # type: ignore[arg-type]
    try:
        events = [ev async for ev in dispatcher.run_turn(conversation, "list my projects")]

        names = [e[EVENT] for e in events]
        assert EVENT_FUNCTION_CALL in names
        assert EVENT_FUNCTION_CALL_OUTPUT in names
        assert names[-1] == EVENT_DONE
        text = "".join(
            e[DATA]["content"] for e in events if e[EVENT] == EVENT_TEXT_DELTA
        )
        assert text == "Here are the projects."

        async with engine.connect() as conn:
            msgs = await MessageRepository(conn).list_for_conversation(
                conversation.conversation_uuid
            )
        kinds = [m.kind for m in msgs]
        assert MessageKind.USER in kinds
        assert MessageKind.FUNCTION_CALL in kinds
        assert MessageKind.FUNCTION_CALL_OUTPUT in kinds
        assert MessageKind.ASSISTANT in kinds

        output = next(m for m in msgs if m.kind == MessageKind.FUNCTION_CALL_OUTPUT)
        assert output.success is True
        assert output.data == {"projects": []}
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                delete(conversations).where(
                    conversations.c.conversation_uuid == conversation.conversation_uuid
                )
            )
            await conn.execute(
                delete(prompt_versions).where(
                    prompt_versions.c.prompt_type == PromptType.DISPATCHER.value,
                    prompt_versions.c.version == 1,
                )
            )
