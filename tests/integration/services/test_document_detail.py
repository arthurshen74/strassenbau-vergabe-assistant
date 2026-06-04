"""DocumentDetailService chunk mapping. The LangChain path touches no database, so it is exercised
here with a fake SearchClient; the SimpleChunk path and counts are ES-backed (verified manually)."""

from __future__ import annotations

from uuid import UUID, uuid4

from shared.clients.search.client import LangchainChunk
from shared.services.document_detail import DocumentDetailService


class _FakeSearch:
    async def list_langchain_chunks(
        self, document_uuid: UUID, *, text: str | None = None, offset: int = 0, size: int = 50
    ) -> tuple[list[LangchainChunk], int]:
        return [LangchainChunk(chunk_id="lc1", page=2, start_index=10, text="hallo welt")], 1


async def test_list_chunks_maps_langchain_results() -> None:
    # engine is unused on the LangChain path.
    service = DocumentDetailService(engine=None, search=_FakeSearch())  # type: ignore[arg-type]
    result = await service.list_chunks(uuid4(), uuid4(), source="langchain")

    assert result.total == 1
    [chunk] = result.items
    assert chunk.source == "langchain"
    assert chunk.chunk_id == "lc1"
    assert chunk.page == 2
    assert chunk.text == "hallo welt"
    assert chunk.chunk_index is None  # langchain chunks have no stored index
    assert chunk.source_doc_type is None
