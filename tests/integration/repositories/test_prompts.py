from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.prompt import NewPrompt
from shared.domain.prompt_version import NewPromptVersion
from shared.repositories.prompts import PromptRepository


def _new_version(**overrides) -> NewPromptVersion:
    base = dict(
        system_prompt="You are a helpful assistant.",
        model_provider="anthropic",
        model_id="claude-sonnet-4-6",
        api_key_ref="ANTHROPIC_API_KEY",
        temperature=0.0,
        max_tokens=1024,
    )
    base.update(overrides)
    return NewPromptVersion(**base)


async def test_add_round_trips_all_fields(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    created = await repo.add(
        NewPrompt(slug="extract_assertions", description="Extract assertions")
    )
    assert created.prompt_uuid is not None
    assert created.slug == "extract_assertions"
    assert created.description == "Extract assertions"
    assert created.is_archived is False


async def test_get_by_slug_returns_prompt(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    created = await repo.add(NewPrompt(slug="chat_rag"))
    fetched = await repo.get_by_slug("chat_rag")
    assert fetched is not None
    assert fetched.prompt_uuid == created.prompt_uuid


async def test_unique_constraint_blocks_duplicate_slug(
    conn: AsyncConnection,
) -> None:
    repo = PromptRepository(conn)
    await repo.add(NewPrompt(slug="dupe_slug"))
    with pytest.raises(IntegrityError):
        await repo.add(NewPrompt(slug="dupe_slug"))


async def test_list_hides_archived_by_default(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    live = await repo.add(NewPrompt(slug="live_prompt"))
    archived = await repo.add(NewPrompt(slug="archived_prompt"))
    await repo.archive(archived.prompt_uuid)

    visible = await repo.list()
    visible_slugs = {p.slug for p in visible}
    assert "live_prompt" in visible_slugs
    assert "archived_prompt" not in visible_slugs

    all_prompts = await repo.list(include_archived=True)
    assert {p.slug for p in all_prompts} >= {"live_prompt", "archived_prompt"}
    assert live.prompt_uuid in {p.prompt_uuid for p in all_prompts}


async def test_archive_and_unarchive(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    created = await repo.add(NewPrompt(slug="toggleable"))
    archived = await repo.archive(created.prompt_uuid)
    assert archived is not None
    assert archived.is_archived is True
    unarchived = await repo.unarchive(created.prompt_uuid)
    assert unarchived is not None
    assert unarchived.is_archived is False


async def test_add_version_auto_increments(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="versioned"))
    v1 = await repo.add_version(prompt.prompt_uuid, _new_version())
    v2 = await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.5))
    v3 = await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.7))
    assert (v1.version, v2.version, v3.version) == (1, 2, 3)


async def test_get_version_by_slug_latest(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="latest_lookup"))
    await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.0))
    await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.5))
    latest = await repo.get_version_by_slug("latest_lookup", "latest")
    assert latest is not None
    assert latest.version == 2
    assert latest.temperature == 0.5


async def test_get_version_by_slug_pinned(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="pinned_lookup"))
    await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.0))
    await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.5))
    pinned = await repo.get_version_by_slug("pinned_lookup", 1)
    assert pinned is not None
    assert pinned.version == 1
    assert pinned.temperature == 0.0


async def test_get_version_by_slug_missing_returns_none(
    conn: AsyncConnection,
) -> None:
    repo = PromptRepository(conn)
    assert await repo.get_version_by_slug("does_not_exist", "latest") is None


async def test_version_round_trips_complex_fields(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="complex_fields"))
    v1 = await repo.add_version(
        prompt.prompt_uuid,
        _new_version(
            stop_sequences=["</answer>", "STOP"],
            tool_selection=["search_lv_items", "get_paragraph"],
            output_schema_ref="AssertionExtractionResult",
            top_p=0.9,
        ),
    )
    assert v1.stop_sequences == ["</answer>", "STOP"]
    assert v1.tool_selection == ["search_lv_items", "get_paragraph"]
    assert v1.output_schema_ref == "AssertionExtractionResult"
    assert v1.top_p == 0.9


async def test_unique_version_per_prompt(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="unique_versions"))
    await repo.add_version(prompt.prompt_uuid, _new_version())
    from sqlalchemy import insert

    from shared.db.tables.prompt_versions import prompt_versions as tbl

    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(tbl).values(
                prompt_uuid=prompt.prompt_uuid,
                version=1,
                **_new_version().model_dump(),
            )
        )


async def test_cascade_delete_removes_versions(conn: AsyncConnection) -> None:
    repo = PromptRepository(conn)
    prompt = await repo.add(NewPrompt(slug="cascade"))
    await repo.add_version(prompt.prompt_uuid, _new_version())
    await repo.add_version(prompt.prompt_uuid, _new_version(temperature=0.3))

    from sqlalchemy import delete, select

    from shared.db.tables.prompt_versions import prompt_versions as tbl
    from shared.db.tables.prompts import prompts

    await conn.execute(delete(prompts).where(prompts.c.prompt_uuid == prompt.prompt_uuid))
    remaining = (
        await conn.execute(select(tbl).where(tbl.c.prompt_uuid == prompt.prompt_uuid))
    ).mappings().all()
    assert remaining == []
