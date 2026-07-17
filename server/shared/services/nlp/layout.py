"""Docling layout inference for the NLP analysis feature.

Runs the Docling layout model over a document's raw PDF and returns labeled regions
in PDF-point coordinates (top-left origin) — the same space as source_lines bboxes,
so the reflow service can join lines to regions by center containment without any
scaling. Results are cached per (document, docling version) in document_layout_regions;
raw PDFs are immutable, so inference runs at most once per model version.

The converter is a lazy module singleton behind a lock: Docling weights load on first
use, never at API boot, and inference is serialized (the model is not thread-safe).
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.storage.client import StorageClient, raw_object_key
from shared.db.unit_of_work import unit_of_work
from shared.models.nlp import DocumentLayout, LayoutRegion

DOCLING_PACKAGE = "docling"

# Docling DocItemLabel values the reflow service maps to block types. Furniture labels
# are also matched by the repetition heuristic; the union decides (design D2).
LABEL_PAGE_HEADER = "page_header"
LABEL_PAGE_FOOTER = "page_footer"
LABEL_SECTION_HEADER = "section_header"
LABEL_TITLE = "title"
LABEL_LIST_ITEM = "list_item"
LABEL_TABLE = "table"
LABEL_DOCUMENT_INDEX = "document_index"
LABEL_CAPTION = "caption"
LABEL_FOOTNOTE = "footnote"

_converter_lock = threading.Lock()
_converter: object | None = None


def layout_model_version() -> str:
    return package_version(DOCLING_PACKAGE)


def _get_converter() -> object:
    """Lazy Docling converter singleton; loads model weights on first call."""
    global _converter
    with _converter_lock:
        if _converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            # Only layout labels are needed; TableFormer cell structure is not.
            options = PdfPipelineOptions(do_ocr=False, do_table_structure=False)
            _converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=options)
                }
            )
        return _converter


def infer_regions(pdf_bytes: bytes) -> list[LayoutRegion]:
    """Run Docling over a PDF and return every item's provenance as point regions."""
    converter = _get_converter()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        Path(f.name).write_bytes(pdf_bytes)
        with _converter_lock:
            result = converter.convert(f.name)  # type: ignore[attr-defined]
    return regions_from_docling(result.document)


def regions_from_docling(doc: object) -> list[LayoutRegion]:
    """Map a DoclingDocument's items to LayoutRegions in top-left-origin points."""
    regions: list[LayoutRegion] = []
    for item in list(doc.texts) + list(doc.tables) + list(doc.pictures):  # type: ignore[attr-defined]
        label = str(item.label)
        for prov in item.prov:
            page = doc.pages[prov.page_no]  # type: ignore[attr-defined]
            bbox = prov.bbox.to_top_left_origin(page.size.height)
            regions.append(
                LayoutRegion(
                    page=prov.page_no,
                    label=label,
                    bbox=(bbox.l, bbox.t, bbox.r, bbox.b),
                )
            )
    return regions


class LayoutService:
    """Cached access to a document's layout regions."""

    def __init__(self, engine: AsyncEngine, storage: StorageClient) -> None:
        self._engine = engine
        self._storage = storage

    async def get_or_infer(self, document_uuid: UUID) -> DocumentLayout:
        model_version = layout_model_version()
        async with unit_of_work(self._engine) as uow:
            cached = await uow.document_layout_regions.get(document_uuid, model_version)
        if cached is not None:
            return cached

        pdf_bytes = await asyncio.to_thread(
            self._storage.get_object, raw_object_key(document_uuid)
        )
        regions = await asyncio.to_thread(infer_regions, pdf_bytes)
        layout = DocumentLayout(
            document_uuid=document_uuid,
            model_version=model_version,
            regions=regions,
        )
        async with unit_of_work(self._engine) as uow:
            await uow.document_layout_regions.put(layout)
        return layout
