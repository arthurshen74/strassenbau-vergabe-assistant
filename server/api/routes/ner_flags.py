from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine, get_llm_client
from shared.clients.llm.client import LLMClient
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import NerFailureCategory, NerFlagKind, NerFlagStatus
from shared.models.ner_flag import (
    NerFlag,
    NerFlagSummary,
    NerFlagUpdate,
    NewNerFlag,
)
from shared.services.nlp.error_analysis import analyze_flag

router = APIRouter(prefix="/ner-flags", tags=["ner-flags"])


@router.post("", response_model=NerFlag, status_code=status.HTTP_201_CREATED)
async def create_flag(
    payload: NewNerFlag,
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
) -> NerFlag:
    """Persist the flag, then run the one-shot analysis synchronously. A failed analysis
    leaves the flag with a null analysis (retriable), still returned."""
    async with unit_of_work(engine) as uow:
        flag = await uow.ner_flags.add(payload)
    return await analyze_flag(flag, engine=engine, llm=llm)


@router.get("", response_model=list[NerFlag])
async def list_flags(
    kind: NerFlagKind | None = None,
    category: NerFailureCategory | None = None,
    flag_status: NerFlagStatus | None = Query(default=None, alias="status"),
    engine: AsyncEngine = Depends(get_engine),
) -> list[NerFlag]:
    async with unit_of_work(engine) as uow:
        return await uow.ner_flags.list(
            kind=kind, category=category, status=flag_status
        )


@router.get("/summary", response_model=NerFlagSummary)
async def flag_summary(engine: AsyncEngine = Depends(get_engine)) -> NerFlagSummary:
    async with unit_of_work(engine) as uow:
        return await uow.ner_flags.category_counts()


@router.patch("/{ner_flag_uuid}", response_model=NerFlag)
async def update_flag(
    ner_flag_uuid: UUID,
    payload: NerFlagUpdate,
    engine: AsyncEngine = Depends(get_engine),
) -> NerFlag:
    changes = payload.model_dump(exclude_unset=True, mode="json")
    async with unit_of_work(engine) as uow:
        updated = await uow.ner_flags.update(ner_flag_uuid, **changes)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ner flag {ner_flag_uuid} not found",
        )
    return updated


@router.post("/{ner_flag_uuid}/analyze", response_model=NerFlag)
async def reanalyze_flag(
    ner_flag_uuid: UUID,
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
) -> NerFlag:
    async with unit_of_work(engine) as uow:
        flag = await uow.ner_flags.get(ner_flag_uuid)
    if flag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ner flag {ner_flag_uuid} not found",
        )
    return await analyze_flag(flag, engine=engine, llm=llm)


@router.delete("/{ner_flag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flag(
    ner_flag_uuid: UUID,
    engine: AsyncEngine = Depends(get_engine),
) -> None:
    async with unit_of_work(engine) as uow:
        await uow.ner_flags.delete(ner_flag_uuid)
