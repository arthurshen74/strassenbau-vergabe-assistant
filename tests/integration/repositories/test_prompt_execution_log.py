from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.llm.execution_log_sinks import DatabaseExecutionLogSink
from shared.db.tables.prompt_execution_log import prompt_execution_log
from shared.models.prompt_execution_log import NewPromptExecutionLog
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository


async def test_add_and_get_round_trip(conn: AsyncConnection) -> None:
    repo = PromptExecutionLogRepository(conn)
    created = await repo.add(
        NewPromptExecutionLog(
            model="anthropic/claude-sonnet-4.6",
            messages=[{"role": "user", "content": "hi"}],
            success=True,
            finish_reason="stop",
            response_text="hello",
            tokens_in=5,
            tokens_out=2,
            prompt_type="project_chat",
            prompt_version=1,
        )
    )
    got = await repo.get(created.log_uuid)
    assert got is not None
    assert got.model == "anthropic/claude-sonnet-4.6"
    assert got.success is True
    assert got.messages == [{"role": "user", "content": "hi"}]
    assert got.tokens_in == 5 and got.tokens_out == 2


async def test_database_sink_writes_independently(engine: AsyncEngine) -> None:
    marker = str(uuid4())
    sink = DatabaseExecutionLogSink(engine)
    await sink.emit(
        ExecutionLogEvent(
            model="x/y",
            messages=[{"role": "user", "content": "hi"}],
            success=True,
            request_id=marker,
        )
    )
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    select(prompt_execution_log).where(
                        prompt_execution_log.c.request_id == marker
                    )
                )
            ).mappings().first()
        assert row is not None
        assert row["model"] == "x/y" and row["success"] is True
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                delete(prompt_execution_log).where(
                    prompt_execution_log.c.request_id == marker
                )
            )
