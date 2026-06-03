"""End-to-end single-shot dispatcher loop against real Postgres with a scripted LLM.

The fake LLM scripts two turns: first a tool call (view_projects), then a text answer. The dispatcher
is stateless -- it persists nothing and has no conversation -- so we assert only the SSE event
sequence and the tool result, then clean up the seeded prompt (committed through the dispatcher's own
short transaction)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.events import Done, StreamEvent, TextDelta, ToolCall, ToolCallsReady
from shared.db.tables.prompt_versions import prompt_versions
from shared.models.enums import PromptType
from shared.models.sse_schema import DATA_RESULT, DATA_SUCCESS, DATA_TOOL_NAME
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

    dispatcher = Dispatcher(_FakeLLM(), engine)  # type: ignore[arg-type]
    try:
        events = [ev async for ev in dispatcher.dispatch("list my projects")]

        names = [e[EVENT] for e in events]
        assert EVENT_FUNCTION_CALL in names
        assert EVENT_FUNCTION_CALL_OUTPUT in names
        assert names[-1] == EVENT_DONE
        text = "".join(
            e[DATA]["content"] for e in events if e[EVENT] == EVENT_TEXT_DELTA
        )
        assert text == "Here are the projects."

        output = next(e for e in events if e[EVENT] == EVENT_FUNCTION_CALL_OUTPUT)
        assert output[DATA][DATA_TOOL_NAME] == "view_projects"
        assert output[DATA][DATA_SUCCESS] is True
        assert output[DATA][DATA_RESULT]["projects"] == []
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                delete(prompt_versions).where(
                    prompt_versions.c.prompt_type == PromptType.DISPATCHER.value,
                    prompt_versions.c.version == 1,
                )
            )
