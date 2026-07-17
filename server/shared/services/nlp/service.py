"""NlpService: composition root for the /nlp/* routes.

Wires document listing, reflow (source_lines + cached layout), spaCy analysis,
and the reflowed-text view together. Route handlers stay thin wrappers.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.storage.client import StorageClient
from shared.db.tables.documents import documents
from shared.db.tables.projects import projects
from shared.db.tables.source_lines import source_lines
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import BlockType, DocumentType
from shared.models.nlp import ReflowResult
from shared.models.nlp_schema import (
    AnalyzeResponse,
    DocumentTextRead,
    NlpDocumentRead,
    SourceLineRead,
)
from shared.models.source_line import SourceLine
from shared.services.nlp.analysis import analyze_blocks, get_nlp
from shared.services.nlp.entity_ruler import ensure_ruler_current
from shared.services.nlp.layout import LayoutService
from shared.services.nlp.reflow import reflow_document


class NlpService:
    def __init__(self, engine: AsyncEngine, storage: StorageClient) -> None:
        self._engine = engine
        self._layout = LayoutService(engine, storage)

    async def list_documents(self) -> list[NlpDocumentRead]:
        stmt = (
            select(
                documents.c.document_uuid,
                documents.c.file_name,
                documents.c.number_of_pages,
                projects.c.project_name,
            )
            .join(projects, projects.c.project_uuid == documents.c.project_uuid)
            .where(
                documents.c.document_type == DocumentType.PROSE_DOCUMENT.value,
                exists(
                    select(source_lines.c.source_line_uuid).where(
                        source_lines.c.document_uuid == documents.c.document_uuid
                    )
                ),
            )
            .order_by(projects.c.project_name, documents.c.file_name)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [NlpDocumentRead.model_validate(dict(r)) for r in rows]

    async def get_reflow(self, document_uuid: UUID) -> tuple[list[SourceLine], ReflowResult]:
        """Load lines, ensure layout regions exist, and reflow (CPU-bound part off-loop)."""
        async with unit_of_work(self._engine) as uow:
            lines = await uow.source_lines.list_by_document(document_uuid)
        layout = await self._layout.get_or_infer(document_uuid)
        result = await asyncio.to_thread(reflow_document, lines, layout.regions)
        return lines, result

    async def document_text(self, document_uuid: UUID) -> DocumentTextRead:
        lines, result = await self.get_reflow(document_uuid)
        return DocumentTextRead(
            document_uuid=document_uuid,
            blocks=result.blocks,
            lines=[
                SourceLineRead(
                    line_id=line.line_id,
                    page=line.page,
                    text=line.line_text,
                    block_type=result.line_types[line.line_id],
                )
                for line in lines
            ],
        )

    async def analyze(
        self, document_uuid: UUID, include_blocks: list[BlockType]
    ) -> AnalyzeResponse:
        _, result = await self.get_reflow(document_uuid)
        await ensure_ruler_current(get_nlp(), self._engine)
        sentences, pos, entities = await asyncio.to_thread(
            analyze_blocks, result.blocks, include_blocks
        )
        return AnalyzeResponse(
            document_uuid=document_uuid,
            include_blocks=include_blocks,
            sentences=sentences,
            pos=pos,
            entities=entities,
        )
