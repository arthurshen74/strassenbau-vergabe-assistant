from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import asyncpg

from shared.config import settings


async def main() -> None:
    databases = (
        settings.postgres_db,
        f"{settings.postgres_db}_auth",
        f"{settings.postgres_db}_test",
    )
    parsed = urlparse(settings.database_url)
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database="postgres",
    )
    try:
        for db in databases:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            if exists:
                print(f"  {db}: exists")
            else:
                await conn.execute(f'CREATE DATABASE "{db}"')
                print(f"  {db}: created")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
