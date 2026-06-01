from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import PromptType
from shared.models.prompt_version_schema import PromptVersionCreate, PromptVersionRead
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.prompt_service import PromptService

router = APIRouter(prefix="/prompts", tags=["prompts"])


def get_prompt_service(
    conn: AsyncConnection = Depends(get_connection),
) -> PromptService:
    return PromptService(PromptVersionRepository(conn))


def get_writable_prompt_service(
    uow: UnitOfWork = Depends(get_uow),
) -> PromptService:
    return PromptService(uow.prompt_versions)


@router.get("/{prompt_type}", response_model=list[PromptVersionRead])
async def list_versions(
    prompt_type: PromptType,
    service: PromptService = Depends(get_prompt_service),
) -> list[PromptVersionRead]:
    return await service.list_versions(prompt_type)


# Declared before /{version} so "latest" is not parsed as a version.
@router.get("/{prompt_type}/latest", response_model=PromptVersionRead)
async def get_latest(
    prompt_type: PromptType,
    service: PromptService = Depends(get_prompt_service),
) -> PromptVersionRead:
    found = await service.get_latest(prompt_type)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no versions for prompt_type {prompt_type}",
        )
    return found


@router.get("/{prompt_type}/{version}", response_model=PromptVersionRead)
async def get_version(
    prompt_type: PromptType,
    version: int,
    service: PromptService = Depends(get_prompt_service),
) -> PromptVersionRead:
    found = await service.get_version(prompt_type, version)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt_type {prompt_type} version {version} not found",
        )
    return found


@router.post("", response_model=PromptVersionRead, status_code=status.HTTP_201_CREATED)
async def create_version(
    payload: PromptVersionCreate,
    service: PromptService = Depends(get_writable_prompt_service),
) -> PromptVersionRead:
    return await service.create_version(payload)
