from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.clients.openrouter.usage import UsageEvent
from shared.clients.openrouter.usage.sinks import DatabaseUsageSink
from shared.db.tables.openrouter_usage import openrouter_usage
from shared.models.conversation import NewConversation
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, PromptType, UsageOperation
from shared.models.openrouter_usage import NewOpenRouterUsage
from shared.models.project import NewProject
from shared.repositories.conversations import ConversationRepository
from shared.repositories.documents import DocumentRepository
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.repositories.projects import ProjectRepository


def _new_chat(project_uuid=None, **overrides) -> NewOpenRouterUsage:
    values = dict(
        operation=UsageOperation.CHAT,
        model="anthropic/claude-sonnet-4.6",
        prompt_tokens=100,
        completion_tokens=40,
        total_tokens=140,
        cost=Decimal("0.00210000"),
        cached_tokens=64,
        reasoning_tokens=12,
        project_uuid=project_uuid,
        request_id="gen-1",
        chat_prompt_type="project_chat",
        chat_prompt_version=3,
    )
    values.update(overrides)
    return NewOpenRouterUsage(**values)


async def _make_project(conn: AsyncConnection):
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-USAGE",
            project_name="Usage Test",
            project_description="cost tracking",
            vergabestelle="LRA",
        )
    )
    return project.project_uuid


async def test_add_and_get_round_trip(conn: AsyncConnection) -> None:
    project_uuid = await _make_project(conn)
    repo = OpenRouterUsageRepository(conn)

    created = await repo.add(_new_chat(project_uuid=project_uuid))
    fetched = await repo.get(created.usage_uuid)

    assert fetched is not None
    assert fetched.operation is UsageOperation.CHAT
    assert fetched.cost == Decimal("0.00210000")
    assert fetched.cached_tokens == 64
    assert fetched.reasoning_tokens == 12
    assert fetched.project_uuid == project_uuid
    assert fetched.chat_prompt_type == "project_chat"
    assert fetched.chat_prompt_version == 3


async def test_add_rerank_without_token_counts(conn: AsyncConnection) -> None:
    repo = OpenRouterUsageRepository(conn)
    created = await repo.add(
        NewOpenRouterUsage(
            operation=UsageOperation.RERANK,
            model="cohere/rerank-v3.5",
            total_tokens=0,
            search_units=1,
            cost=Decimal("0.00200000"),
        )
    )
    fetched = await repo.get(created.usage_uuid)

    assert fetched is not None
    assert fetched.prompt_tokens is None
    assert fetched.completion_tokens is None
    assert fetched.search_units == 1
    assert fetched.cost == Decimal("0.00200000")


async def test_add_without_cost_records_none(conn: AsyncConnection) -> None:
    repo = OpenRouterUsageRepository(conn)
    created = await repo.add(
        NewOpenRouterUsage(
            operation=UsageOperation.EMBEDDING,
            model="openai/text-embedding-3-small",
            prompt_tokens=8,
            total_tokens=8,
        )
    )
    fetched = await repo.get(created.usage_uuid)
    assert fetched is not None
    assert fetched.cost is None


async def test_get_missing_returns_none(conn: AsyncConnection) -> None:
    assert await OpenRouterUsageRepository(conn).get(uuid4()) is None


async def test_add_with_document_and_conversation_attribution(conn: AsyncConnection) -> None:
    project_uuid = await _make_project(conn)
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    convo = await ConversationRepository(conn).add(
        NewConversation(
            user_uuid=uuid4(),
            prompt_type=PromptType.PROJECT_CHAT,
            project_uuid=project_uuid,
        )
    )
    repo = OpenRouterUsageRepository(conn)

    created = await repo.add(
        _new_chat(
            project_uuid=project_uuid,
            document_uuid=doc.document_uuid,
            conversation_uuid=convo.conversation_uuid,
        )
    )
    fetched = await repo.get(created.usage_uuid)

    assert fetched is not None
    assert fetched.document_uuid == doc.document_uuid
    assert fetched.conversation_uuid == convo.conversation_uuid


async def test_list_by_project_filters(conn: AsyncConnection) -> None:
    repo = OpenRouterUsageRepository(conn)
    project_a = await _make_project(conn)

    await repo.add(_new_chat(project_uuid=project_a))
    await repo.add(_new_chat(project_uuid=project_a, request_id="gen-2"))
    await repo.add(_new_chat(project_uuid=None, request_id="gen-3"))

    rows = await repo.list_by_project(project_a)
    assert len(rows) == 2
    assert all(r.project_uuid == project_a for r in rows)


async def test_database_sink_writes_in_own_transaction(engine: AsyncEngine) -> None:
    # The sink commits via its own engine.begin(); use a unique request_id and clean up after.
    request_id = f"sink-{uuid4()}"
    event = UsageEvent(
        operation=UsageOperation.CHAT,
        model="anthropic/claude-sonnet-4.6",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost=Decimal("0.00010000"),
        request_id=request_id,
    )

    await DatabaseUsageSink(engine).emit(event)

    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    openrouter_usage.select().where(
                        openrouter_usage.c.request_id == request_id
                    )
                )
            ).mappings().all()
        assert len(rows) == 1
        assert rows[0]["operation"] == UsageOperation.CHAT.value
        assert rows[0]["total_tokens"] == 15
        assert rows[0]["cost"] == Decimal("0.00010000")
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                delete(openrouter_usage).where(
                    openrouter_usage.c.request_id == request_id
                )
            )
