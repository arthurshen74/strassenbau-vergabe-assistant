from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine, get_storage
from shared.clients.storage.client import StorageClient
from shared.models.nlp_schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    DocumentTextRead,
    NlpDocumentRead,
    RenderRequest,
    RenderResponse,
)
from shared.services.nlp.render import RenderService
from shared.services.nlp.service import NlpService

router = APIRouter(prefix="/nlp", tags=["nlp"])


def get_nlp_service(
    engine: AsyncEngine = Depends(get_engine),
    storage: StorageClient = Depends(get_storage),
) -> NlpService:
    return NlpService(engine, storage)


def get_render_service(engine: AsyncEngine = Depends(get_engine)) -> RenderService:
    return RenderService(engine)


@router.get("/documents", response_model=list[NlpDocumentRead])
async def list_documents(
    service: NlpService = Depends(get_nlp_service),
) -> list[NlpDocumentRead]:
    return await service.list_documents()


@router.get("/documents/{document_uuid}/text", response_model=DocumentTextRead)
async def document_text(
    document_uuid: UUID,
    service: NlpService = Depends(get_nlp_service),
) -> DocumentTextRead:
    return await service.document_text(document_uuid)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    service: NlpService = Depends(get_nlp_service),
) -> AnalyzeResponse:
    return await service.analyze(
        request.document_uuid, request.text, request.include_blocks
    )


@router.post("/render", response_model=RenderResponse)
async def render(
    request: RenderRequest,
    service: RenderService = Depends(get_render_service),
) -> RenderResponse:
    markup = await service.render(request.style, request.text)
    return RenderResponse(style=request.style, markup=markup)
