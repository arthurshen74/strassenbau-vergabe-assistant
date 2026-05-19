from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_DATABASES = ("roadbuilders", "roadbuilders_auth", "roadbuilders_test")

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class _BootstrapConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str


async def main() -> None:
    config = _BootstrapConfig()  # type: ignore[call-arg]
    parsed = urlparse(config.database_url)
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database="postgres",
    )
    try:
        for db in REQUIRED_DATABASES:
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
