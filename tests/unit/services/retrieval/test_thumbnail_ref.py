from __future__ import annotations

from uuid import uuid4

import pytest

from shared.models.enums import SourceDocType
from shared.models.simple_chunk import SimpleChunk
from shared.services.retrieval.service import _thumbnail_ref


def _chunk(source_doc_type: SourceDocType, pages: list[int]) -> SimpleChunk:
    return SimpleChunk(
        chunk_uuid=uuid4(),
        source_doc_uuid=uuid4(),
        source_doc_type=source_doc_type,
        source_doc_field="f",
        source_doc_pages=pages,
        chunk_index=0,
        project_uuid=uuid4(),
        chunk_text="t",
        embedding=[0.0],
        embedding_model="m",
    )


@pytest.mark.parametrize("doc_type", [SourceDocType.DOCUMENT, SourceDocType.FORM])
def test_paged_chunks_cite_their_first_page(doc_type: SourceDocType) -> None:
    chunk = _chunk(doc_type, [3, 4])
    ref = _thumbnail_ref(chunk)
    assert ref is not None
    assert (ref.document_uuid, ref.page_number) == (chunk.source_doc_uuid, 3)


@pytest.mark.parametrize("doc_type", [SourceDocType.LV_ITEM, SourceDocType.LV_TEXT])
def test_lv_chunks_have_no_thumbnail(doc_type: SourceDocType) -> None:
    assert _thumbnail_ref(_chunk(doc_type, [1])) is None
