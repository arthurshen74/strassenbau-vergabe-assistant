"""Create the domain schema (all Core tables) on the main database.

Runs after `bootstrap_dbs` (which only creates the databases). Importing
`shared.db.tables` registers every table on the shared metadata; `create_all` is
idempotent (checkfirst), so re-running on each startup is a no-op once the schema is in
place.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

import shared.db.tables  # noqa: F401 -- registers all tables on the shared metadata
from shared.config import settings
from shared.db.metadata import metadata


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        print(f"  schema: {len(metadata.tables)} tables ensured")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
