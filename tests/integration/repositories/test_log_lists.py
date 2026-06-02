from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import UsageOperation
from shared.models.openrouter_usage import NewOpenRouterUsage
from shared.models.prompt_execution_log import NewPromptExecutionLog
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository


async def test_execution_log_list_filters_and_pages(conn: AsyncConnection) -> None:
    repo = PromptExecutionLogRepository(conn)
    for _ in range(3):
        await repo.add(
            NewPromptExecutionLog(model="m", messages=[], success=True, prompt_type="dispatcher")
        )
    await repo.add(
        NewPromptExecutionLog(model="m", messages=[], success=True, prompt_type="project_chat")
    )

    dispatcher_rows = await repo.list(prompt_type="dispatcher")
    assert len(dispatcher_rows) == 3
    assert all(r.prompt_type == "dispatcher" for r in dispatcher_rows)

    assert len(await repo.list(limit=2)) == 2
    assert len(await repo.list(limit=2, offset=2)) == 2  # 4 rows total


async def test_usage_list_filters_by_operation(conn: AsyncConnection) -> None:
    repo = OpenRouterUsageRepository(conn)
    await repo.add(NewOpenRouterUsage(operation=UsageOperation.CHAT, model="m", total_tokens=1))
    await repo.add(
        NewOpenRouterUsage(operation=UsageOperation.EMBEDDING, model="m", total_tokens=1)
    )

    chat = await repo.list(operation=UsageOperation.CHAT)
    assert len(chat) == 1
    assert chat[0].operation is UsageOperation.CHAT
    assert len(await repo.list()) == 2
