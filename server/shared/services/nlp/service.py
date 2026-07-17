"""NlpService: composition root for the /nlp/* routes.

Wires reflow (source_lines + cached layout), spaCy analysis, and the reflowed-text view
together. Route handlers stay thin wrappers.
"""

from __future__ import annotations

import asyncio
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.storage.client import StorageClient
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import BlockType
from shared.models.nlp import ReflowedBlock, ReflowResult
from shared.models.nlp_schema import (
    AnalyzeResponse,
    DocumentTextRead,
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

    async def get_reflow(
        self, document_uuid: UUID
    ) -> tuple[list[SourceLine], ReflowResult]:
        """Load lines, ensure layout regions exist, and reflow (CPU-bound part
        off-loop)."""
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
        self,
        document_uuid: UUID | None,
        text: str | None,
        include_blocks: list[BlockType],
    ) -> AnalyzeResponse:
        if text is not None:
            blocks = _blocks_from_text(text)
        else:
            _, result = await self.get_reflow(document_uuid)
            blocks = result.blocks
        await ensure_ruler_current(get_nlp(), self._engine)
        sentences, pos, entities, ent_html = await asyncio.to_thread(
            analyze_blocks, blocks, include_blocks
        )
        return AnalyzeResponse(
            document_uuid=document_uuid,
            include_blocks=include_blocks,
            sentences=sentences,
            pos=pos,
            entities=entities,
            ent_html=ent_html,
        )


def _blocks_from_text(text: str) -> list[ReflowedBlock]:
    """Split ad-hoc text on blank lines into PROSE blocks — no layout, no reflow."""
    chunks = [c.strip() for c in re.split(r"\n[ \t]*\n", text)]
    return [
        ReflowedBlock(
            block_id=index,
            block_type=BlockType.PROSE,
            text=chunk,
            page_start=1,
            page_end=1,
            line_ids=[],
        )
        for index, chunk in enumerate(c for c in chunks if c)
    ]
