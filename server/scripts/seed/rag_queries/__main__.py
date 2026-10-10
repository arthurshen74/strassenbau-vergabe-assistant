"""Seed RagQueryVersions from the `.yaml` files in this package.

NOT idempotent: each run appends a new version per (query_key, language), with the
repository assigning the next integer (version 1 when none exist yet). Edit a `.yaml`
file and re-run to publish the next version. Run with
`PYTHONPATH=server uv run python -m scripts.seed.rag_queries`.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from scripts.seed.rag_queries import load_rag_query_versions
from shared.config import settings
from shared.db.engine import make_engine
from shared.repositories.rag_queries import RagQueryVersionRepository


async def _seed(conn: AsyncConnection) -> None:
    repo = RagQueryVersionRepository(conn)
    for new in load_rag_query_versions():
        created = await repo.add(new)
        print(
            f"  {created.query_key.value}.{created.language}: added v{created.version}"
        )


async def main() -> None:
    engine: AsyncEngine = make_engine(
        settings.database_url, pool_size=2, application_name="seed-rag-queries"
    )
    try:
        async with engine.begin() as conn:
            await _seed(conn)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
