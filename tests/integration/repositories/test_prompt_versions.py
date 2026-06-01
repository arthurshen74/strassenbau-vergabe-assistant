from __future__ import annotations

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.prompt_versions import prompt_versions
from shared.models.chat_message import ChatMessage
from shared.models.enums import PromptType
from shared.models.prompt_version import NewPromptVersion
from shared.repositories.prompt_versions import PromptVersionRepository


def _new(prompt_type: PromptType, **kw: object) -> NewPromptVersion:
    return NewPromptVersion(
        prompt_type=prompt_type,
        model_name="anthropic/claude-sonnet-4.6",
        system_prompt="You are helpful.",
        **kw,
    )


async def test_version_auto_increments_per_type(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    first = await repo.add(_new(PromptType.PROJECT_CHAT))
    second = await repo.add(_new(PromptType.PROJECT_CHAT))
    other = await repo.add(_new(PromptType.DISPATCHER))

    assert first.version == 1
    assert second.version == 2
    # Versions are scoped per prompt_type, so a different type starts again at 1.
    assert other.version == 1


async def test_get_latest_and_by_type_and_version(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    v1 = await repo.add(_new(PromptType.DISPATCHER))
    v2 = await repo.add(_new(PromptType.DISPATCHER))

    latest = await repo.get_latest(PromptType.DISPATCHER)
    assert latest is not None
    assert latest.prompt_version_uuid == v2.prompt_version_uuid

    fetched = await repo.get_by_type_and_version(PromptType.DISPATCHER, 1)
    assert fetched is not None
    assert fetched.prompt_version_uuid == v1.prompt_version_uuid

    listed = await repo.list_by_type(PromptType.DISPATCHER)
    assert [v.version for v in listed] == [1, 2]


async def test_get_latest_none_when_absent(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    assert await repo.get_latest(PromptType.LV_EXTRACTION) is None


async def test_initial_messages_jsonb_round_trip(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    messages = [
        ChatMessage(role="user", content="Wie hoch ist die Menge?"),
        ChatMessage(role="assistant", content="1,5 m"),
    ]
    created = await repo.add(
        _new(PromptType.MULTI_QUESTION_GENERATOR, initial_messages=messages)
    )
    fetched = await repo.get_by_type_and_version(
        PromptType.MULTI_QUESTION_GENERATOR, created.version
    )
    assert fetched is not None
    assert fetched.initial_messages == messages


async def test_prompt_type_version_unique(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    await repo.add(_new(PromptType.CLASSIFY_PROJECT_CHAT_USER_MESSAGE))
    # A hand-rolled duplicate of (prompt_type, version) must violate the unique.
    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(prompt_versions).values(
                prompt_type=PromptType.CLASSIFY_PROJECT_CHAT_USER_MESSAGE.value,
                version=1,
                model_name="m",
                system_prompt="s",
                temperature=0.0,
            )
        )
