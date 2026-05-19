from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.eval_test_set import NewEvalTestSet
from shared.repositories.eval_test_sets import EvalTestSetRepository


async def test_add_round_trips_all_fields(conn: AsyncConnection) -> None:
    repo = EvalTestSetRepository(conn)
    created = await repo.add(
        NewEvalTestSet(
            name="ChunkLoaderV3",
            description="Baseline with chunk size 1024",
            config={"chunk_size": 1024, "embedding_model": "bge-small"},
        )
    )
    assert created.test_set_uuid is not None
    assert created.name == "ChunkLoaderV3"
    assert created.config["chunk_size"] == 1024


async def test_get_by_name_returns_test_set(conn: AsyncConnection) -> None:
    repo = EvalTestSetRepository(conn)
    created = await repo.add(NewEvalTestSet(name="BaselineV1"))
    fetched = await repo.get_by_name("BaselineV1")
    assert fetched is not None
    assert fetched.test_set_uuid == created.test_set_uuid


async def test_unique_constraint_blocks_duplicate_name(
    conn: AsyncConnection,
) -> None:
    repo = EvalTestSetRepository(conn)
    await repo.add(NewEvalTestSet(name="DupeName"))
    with pytest.raises(IntegrityError):
        await repo.add(NewEvalTestSet(name="DupeName"))


async def test_default_config_is_empty_dict(conn: AsyncConnection) -> None:
    repo = EvalTestSetRepository(conn)
    created = await repo.add(NewEvalTestSet(name="MinimalSet"))
    assert created.config == {}
