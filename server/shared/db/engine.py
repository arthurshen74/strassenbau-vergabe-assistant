from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(
    database_url: str,
    *,
    pool_size: int,
    application_name: str,
    pool_recycle: int = 1800,
    pool_pre_ping: bool = True,
) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=pool_size,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        connect_args={"server_settings": {"application_name": application_name}},
    )
