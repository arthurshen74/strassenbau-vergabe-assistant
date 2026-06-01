"""Seed PromptVersions from the `.prompt` files in this package.

NOT idempotent: each run appends a new version per prompt type, with the repository
assigning the next integer (version 1 when none exist yet). Edit a `.prompt` file and
re-run to publish the next version. Run with `python -m scripts.seed.prompts` (or via
docker compose against the compose DB).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from scripts.seed.prompts import load_prompt_versions
from shared.config import settings
from shared.db.engine import make_engine
from shared.repositories.prompt_versions import PromptVersionRepository


async def _seed(conn: AsyncConnection) -> None:
    repo = PromptVersionRepository(conn)
    for new in load_prompt_versions():
        created = await repo.add(new)
        print(f"  {created.prompt_type.value}: added v{created.version}")


async def main() -> None:
    engine: AsyncEngine = make_engine(
        settings.database_url, pool_size=2, application_name="seed-prompts"
    )
    try:
        async with engine.begin() as conn:
            await _seed(conn)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
