from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine
from shared.models.entity_rule_schema import (
    EntityRuleCreate,
    EntityRuleRead,
    EntityRuleUpdate,
)
from shared.services.nlp.entity_rule_service import EntityRuleService

router = APIRouter(prefix="/entity-rules", tags=["entity-rules"])


def get_entity_rule_service(
    engine: AsyncEngine = Depends(get_engine),
) -> EntityRuleService:
    return EntityRuleService(engine)


@router.get("", response_model=list[EntityRuleRead])
async def list_rules(
    service: EntityRuleService = Depends(get_entity_rule_service),
) -> list[EntityRuleRead]:
    return await service.list()


# Declared before /{entity_rule_uuid} so "labels" is not parsed as a uuid.
@router.get("/labels", response_model=list[str])
async def list_labels(
    service: EntityRuleService = Depends(get_entity_rule_service),
) -> list[str]:
    return await service.labels()


@router.post("", response_model=EntityRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: EntityRuleCreate,
    service: EntityRuleService = Depends(get_entity_rule_service),
) -> EntityRuleRead:
    try:
        return await service.create(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.patch("/{entity_rule_uuid}", response_model=EntityRuleRead)
async def update_rule(
    entity_rule_uuid: UUID,
    payload: EntityRuleUpdate,
    service: EntityRuleService = Depends(get_entity_rule_service),
) -> EntityRuleRead:
    try:
        updated = await service.update(entity_rule_uuid, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity rule {entity_rule_uuid} not found",
        )
    return updated


@router.delete("/{entity_rule_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    entity_rule_uuid: UUID,
    service: EntityRuleService = Depends(get_entity_rule_service),
) -> None:
    await service.delete(entity_rule_uuid)
