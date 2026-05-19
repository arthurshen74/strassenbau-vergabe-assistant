from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine

router = APIRouter()


@router.get("/health")
async def health(engine: AsyncEngine = Depends(get_engine)) -> dict[str, str]:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        result.scalar_one()
    return {"status": "ok"}
