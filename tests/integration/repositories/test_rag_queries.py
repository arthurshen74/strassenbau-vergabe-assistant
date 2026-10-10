from __future__ import annotations

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.rag_query_versions import rag_query_versions
from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query import NewRagQueryVersion
from shared.repositories.rag_queries import RagQueryVersionRepository

DE = "de"
EN = "en"


def _new(
    query_key: ProjectInfoQuery, language: str = DE, text: str = "Frage?"
) -> NewRagQueryVersion:
    return NewRagQueryVersion(
        query_key=query_key,
        language=language,
        name="Name",
        description="Beschreibung",
        query_text=text,
        answer_instruction="Nur den Wert.",
    )


async def test_version_increments_per_key_and_language(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    first = await repo.add(_new(ProjectInfoQuery.PROJECT_NAME))
    second = await repo.add(_new(ProjectInfoQuery.PROJECT_NAME))
    other_key = await repo.add(_new(ProjectInfoQuery.PROJECT_LOCATION))

    assert (first.version, second.version) == (1, 2)
    assert other_key.version == 1


async def test_languages_do_not_share_version_counters(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, DE))
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, DE))
    english = await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, EN))

    assert english.version == 1
    latest_de = await repo.get_latest(ProjectInfoQuery.PROJECT_NAME, DE)
    assert latest_de is not None and latest_de.version == 2


async def test_get_latest_none_when_absent(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, DE))
    assert await repo.get_latest(ProjectInfoQuery.PROJECT_NAME, EN) is None
    assert await repo.get_latest(ProjectInfoQuery.PROJECT_LOCATION, DE) is None


async def test_latest_all_returns_one_row_per_key(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, text="v1"))
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME, text="v2"))
    await repo.add(_new(ProjectInfoQuery.PROJECT_LOCATION, text="loc"))
    await repo.add(_new(ProjectInfoQuery.PROJECT_BAULEISTUNG, EN))

    latest = await repo.latest_all(DE)

    by_key = {v.query_key: v for v in latest}
    assert len(latest) == len(by_key) == 2
    assert by_key[ProjectInfoQuery.PROJECT_NAME].query_text == "v2"
    assert by_key[ProjectInfoQuery.PROJECT_LOCATION].version == 1


async def test_history_newest_first(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    for _ in range(3):
        await repo.add(_new(ProjectInfoQuery.PROJECT_VERGABENUMMER))
    await repo.add(_new(ProjectInfoQuery.PROJECT_VERGABENUMMER, EN))

    history = await repo.history(ProjectInfoQuery.PROJECT_VERGABENUMMER, DE)
    assert [v.version for v in history] == [3, 2, 1]


async def test_key_language_version_unique(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    await repo.add(_new(ProjectInfoQuery.PROJECT_NAME))
    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(rag_query_versions).values(
                **_new(ProjectInfoQuery.PROJECT_NAME).model_dump(), version=1
            )
        )


async def test_language_check_rejects_upper_case(conn: AsyncConnection) -> None:
    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(rag_query_versions).values(
                **_new(ProjectInfoQuery.PROJECT_NAME, "DE").model_dump(), version=1
            )
        )
