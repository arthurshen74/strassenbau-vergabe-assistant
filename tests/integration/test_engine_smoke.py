from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def test_select_one(conn: AsyncConnection) -> None:
    result = await conn.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
