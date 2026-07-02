"""Katalog endpoints (thin wrappers over KatalogService).

Reads expose the active catalog and the open draft bundles; writes validate, save, activate or
discard a `RezeptBundle`. All logic lives in `shared.services.katalog`; these handlers only shape
requests/responses and map service errors to HTTP status codes.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from api.deps import Principal, get_current_user, get_katalog_service
from shared.models.katalog import (
    BundleBericht,
    KatalogEntitaet,
    KatalogZeile,
    RezeptBundle,
)
from shared.services.katalog.service import (
    BundleNichtGefunden,
    BundleUngueltig,
    KatalogService,
)

router = APIRouter(prefix="/katalog", tags=["katalog"])

# Author recorded on seed-independent catalog edits until real auth lands.
DEFAULT_AUTOR = "kalkulator"


class BundleGespeichert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_uuid: UUID
    bericht: BundleBericht


class BundleEntwurfAnsicht(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_uuid: UUID
    gruppen: dict[KatalogEntitaet, list[KatalogZeile]]


@router.get("/entwuerfe", response_model=list[BundleEntwurfAnsicht])
async def liste_entwuerfe(
    service: KatalogService = Depends(get_katalog_service),
) -> list[BundleEntwurfAnsicht]:
    """Open draft bundles, grouped by bundle then entity."""
    gruppiert = await service.entwuerfe_nach_bundle()
    return [
        BundleEntwurfAnsicht(bundle_uuid=bundle_uuid, gruppen=gruppen)
        for bundle_uuid, gruppen in gruppiert.items()
    ]


@router.get("/{entitaet}", response_model=list[KatalogZeile])
async def liste_aktive(
    entitaet: KatalogEntitaet,
    service: KatalogService = Depends(get_katalog_service),
) -> list[KatalogZeile]:
    """The active rows of one catalog entity (envelope form)."""
    return await service.aktive(entitaet)


@router.post("/bundle/pruefen", response_model=BundleBericht)
async def bundle_pruefen(
    bundle: RezeptBundle,
    service: KatalogService = Depends(get_katalog_service),
) -> BundleBericht:
    """Validate a bundle against the active catalog without writing."""
    return await service.pruefen(bundle)


@router.post("/bundle", response_model=BundleGespeichert)
async def bundle_speichern(
    bundle: RezeptBundle,
    service: KatalogService = Depends(get_katalog_service),
    _principal: Principal = Depends(get_current_user),
) -> BundleGespeichert:
    """Validate and save a bundle as drafts sharing one bundle_uuid."""
    bericht = await service.pruefen(bundle)
    try:
        bundle_uuid = await service.entwurf_speichern(bundle, benutzer=DEFAULT_AUTOR)
    except BundleUngueltig as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.bericht.model_dump()
        ) from exc
    return BundleGespeichert(bundle_uuid=bundle_uuid, bericht=bericht)


@router.post("/bundle/{bundle_uuid}/aktivieren", response_model=BundleBericht)
async def bundle_aktivieren(
    bundle_uuid: UUID,
    service: KatalogService = Depends(get_katalog_service),
    _principal: Principal = Depends(get_current_user),
) -> BundleBericht:
    """Activate a draft bundle atomically and reload the provider."""
    try:
        return await service.bundle_aktivieren(bundle_uuid)
    except BundleNichtGefunden as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BundleUngueltig as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.bericht.model_dump()
        ) from exc


@router.post("/bundle/{bundle_uuid}/verwerfen", status_code=status.HTTP_204_NO_CONTENT)
async def bundle_verwerfen(
    bundle_uuid: UUID,
    service: KatalogService = Depends(get_katalog_service),
    _principal: Principal = Depends(get_current_user),
) -> None:
    """Archive a draft bundle."""
    try:
        await service.bundle_verwerfen(bundle_uuid)
    except BundleNichtGefunden as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
