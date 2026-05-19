from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.schemas.prompt import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    PromptVersionCreate,
    PromptVersionRead,
)
from shared.domain.prompt import NewPrompt
from shared.domain.prompt_version import NewPromptVersion
from shared.repositories.prompts import PromptRepository

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptRead])
async def list_prompts(
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: AsyncConnection = Depends(get_connection),
) -> list[PromptRead]:
    repo = PromptRepository(conn)
    rows = await repo.list(
        include_archived=include_archived, limit=limit, offset=offset
    )
    return [PromptRead.model_validate(p.model_dump()) for p in rows]


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    conn: AsyncConnection = Depends(get_uow),
) -> PromptRead:
    repo = PromptRepository(conn)
    try:
        created = await repo.add(NewPrompt(**payload.model_dump()))
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"prompt with slug {payload.slug!r} already exists",
        ) from exc
    return PromptRead.model_validate(created.model_dump())


@router.get("/{slug}", response_model=PromptRead)
async def get_prompt(
    slug: str,
    conn: AsyncConnection = Depends(get_connection),
) -> PromptRead:
    prompt = await PromptRepository(conn).get_by_slug(slug)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt {slug!r} not found",
        )
    return PromptRead.model_validate(prompt.model_dump())


@router.patch("/{slug}", response_model=PromptRead)
async def update_prompt(
    slug: str,
    payload: PromptUpdate,
    conn: AsyncConnection = Depends(get_uow),
) -> PromptRead:
    repo = PromptRepository(conn)
    prompt = await repo.get_by_slug(slug)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt {slug!r} not found",
        )
    changes = payload.model_dump(exclude_unset=True)
    updated = await repo.update(prompt.prompt_uuid, **changes)
    assert updated is not None
    return PromptRead.model_validate(updated.model_dump())


@router.get("/{slug}/versions", response_model=list[PromptVersionRead])
async def list_prompt_versions(
    slug: str,
    conn: AsyncConnection = Depends(get_connection),
) -> list[PromptVersionRead]:
    repo = PromptRepository(conn)
    prompt = await repo.get_by_slug(slug)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt {slug!r} not found",
        )
    versions = await repo.list_versions(prompt.prompt_uuid)
    return [PromptVersionRead.model_validate(v.model_dump()) for v in versions]


@router.get("/{slug}/versions/{version}", response_model=PromptVersionRead)
async def get_prompt_version(
    slug: str,
    version: int | Literal["latest"],
    conn: AsyncConnection = Depends(get_connection),
) -> PromptVersionRead:
    found = await PromptRepository(conn).get_version_by_slug(slug, version)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"version {version!r} of prompt {slug!r} not found",
        )
    return PromptVersionRead.model_validate(found.model_dump())


@router.post(
    "/{slug}/versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt_version(
    slug: str,
    payload: PromptVersionCreate,
    conn: AsyncConnection = Depends(get_uow),
) -> PromptVersionRead:
    repo = PromptRepository(conn)
    prompt = await repo.get_by_slug(slug)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt {slug!r} not found",
        )
    created = await repo.add_version(
        prompt.prompt_uuid, NewPromptVersion(**payload.model_dump())
    )
    return PromptVersionRead.model_validate(created.model_dump())
