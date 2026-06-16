"""Ranking and collapse logic of LVItemSearchService.search.

Exact oz/stl_nr hits lead, then the RRF of dense + lexical. The ranked chunks are collapsed to
their distinct LV item (an item owns many chunks), capped at the limit, the rows loaded, and
re-ordered by relevance; a ranked id with no row (ES vs DB skew) is dropped. The Elasticsearch
queries themselves are covered by the integration search tests, so the collaborators are faked.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from shared.clients.search import ScoredChunk
from shared.models.enums import SourceDocType
from shared.models.lv_item import LVItem
from shared.models.simple_chunk import SimpleChunk
from shared.services.lv_item_search import LVItemSearchService

PROJECT = uuid4()
DOC = uuid4()


def _scored(source_doc_uuid: UUID, *, oz: str | None = None) -> ScoredChunk:
    """A LV_ITEM ScoredChunk for the given item; chunk_uuid is unique so two chunks of one
    item are distinct rows in Elasticsearch (and so in RRF)."""
    chunk = SimpleChunk(
        chunk_uuid=uuid4(),
        source_doc_uuid=source_doc_uuid,
        source_doc_type=SourceDocType.LV_ITEM,
        source_doc_field="f",
        chunk_index=0,
        oz=oz,
        project_uuid=PROJECT,
        chunk_text="x",
        embedding=[0.0],
        embedding_model="m",
    )
    return ScoredChunk(chunk=chunk, score=1.0)


def _item(lv_item_uuid: UUID, oz: str) -> LVItem:
    return LVItem(
        lv_item_uuid=lv_item_uuid,
        document_uuid=DOC,
        oz=oz,
        kurztext="k",
        langtext="l",
        menge=Decimal("1"),
        einheit="m2",
        last_ingestion=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str], **_: object) -> list[list[float]]:
        self.calls += 1
        return [[0.1] for _ in texts]


class _FakeSearch:
    def __init__(
        self,
        *,
        exact: list[ScoredChunk],
        dense: list[ScoredChunk],
        lexical: list[ScoredChunk],
    ) -> None:
        self._exact = exact
        self._dense = dense
        self._lexical = lexical

    async def keyword_search(self, *_a: object, **_k: object) -> list[ScoredChunk]:
        return self._exact

    async def knn_search(self, *_a: object, **_k: object) -> list[ScoredChunk]:
        return self._dense

    async def lexical_search(self, *_a: object, **_k: object) -> list[ScoredChunk]:
        return self._lexical


class _FakeEngine:
    def connect(self) -> contextlib.AbstractAsyncContextManager[object]:
        @contextlib.asynccontextmanager
        async def _cm() -> object:
            yield object()

        return _cm()


def _patch_repo(monkeypatch: pytest.MonkeyPatch, items: list[LVItem]) -> None:
    by_uuid = {item.lv_item_uuid: item for item in items}

    class _FakeRepo:
        def __init__(self, _conn: object) -> None: ...

        async def list_by_uuids(self, uuids: Sequence[UUID]) -> list[LVItem]:
            # Returned in arbitrary order (reversed) to prove the service re-orders by relevance.
            return [by_uuid[u] for u in reversed(list(uuids)) if u in by_uuid]

    monkeypatch.setattr("shared.services.lv_item_search.LVItemRepository", _FakeRepo)


def _service(embeddings: _FakeEmbeddings, search: _FakeSearch) -> LVItemSearchService:
    return LVItemSearchService(engine=_FakeEngine(), embeddings=embeddings, search=search)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_exact_leads_then_rrf_collapsed_by_item_missing_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ua, ub, uc, ud = uuid4(), uuid4(), uuid4(), uuid4()
    search = _FakeSearch(
        exact=[_scored(uc, oz="01.02.003")],
        # ua twice (two chunks of one item) plus ud, which has no row.
        dense=[_scored(ua), _scored(ub), _scored(ua), _scored(ud)],
        lexical=[_scored(ua), _scored(ub)],
    )
    embeddings = _FakeEmbeddings()
    _patch_repo(monkeypatch, [_item(ua, "10"), _item(ub, "20"), _item(uc, "01.02.003")])

    result = await _service(embeddings, search).search(PROJECT, "  Asphalt  ", limit=10)

    # uc (exact) first; then ua before ub (top of both fused lists); ua collapsed to one; ud dropped.
    assert [i.lv_item_uuid for i in result] == [uc, ua, ub]
    assert embeddings.calls == 1


@pytest.mark.asyncio
async def test_limit_caps_distinct_items(monkeypatch: pytest.MonkeyPatch) -> None:
    ua, ub, uc = uuid4(), uuid4(), uuid4()
    search = _FakeSearch(
        exact=[_scored(uc, oz="01")],
        dense=[_scored(ua), _scored(ub)],
        lexical=[],
    )
    _patch_repo(monkeypatch, [_item(ua, "10"), _item(ub, "20"), _item(uc, "01")])

    result = await _service(_FakeEmbeddings(), search).search(PROJECT, "x", limit=2)

    assert [i.lv_item_uuid for i in result] == [uc, ua]


@pytest.mark.asyncio
async def test_blank_query_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    embeddings = _FakeEmbeddings()
    search = _FakeSearch(exact=[], dense=[], lexical=[])
    _patch_repo(monkeypatch, [])

    result = await _service(embeddings, search).search(PROJECT, "   ", limit=10)

    assert result == []
    assert embeddings.calls == 0
