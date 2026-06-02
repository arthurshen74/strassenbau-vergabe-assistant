"""Live integration tests for the Elasticsearch SimpleChunk client.

Runs against the docker-compose Elasticsearch (8.15). The whole module is skipped when
`settings.elasticsearch_url` is unreachable, so offline unit runs stay green. Each test
gets a fresh, uniquely-named index that is torn down afterwards (the archive index too),
so tests never collide with the real index or each other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch

from shared.clients.search.client import (
    FIELD_ARCHIVED_AT,
    FIELD_CHUNK_TEXT,
    FIELD_SOURCE_DOC_UUID,
    NODE_CLASS,
    SearchClient,
    plus_filter,
    simple_filter,
)
from shared.config import settings
from shared.models.enums import SourceDocType
from shared.models.simple_chunk import NewSimpleChunk


def _make_vec(seed: int) -> list[float]:
    """A deterministic, non-zero embedding of the configured dimension."""
    dim = settings.embedding_dim
    vec = [0.0] * dim
    vec[seed % dim] = 1.0
    vec[(seed * 3 + 1) % dim] = 0.5
    return vec


def _new_chunk(
    *,
    project_uuid: UUID,
    source_doc_uuid: UUID,
    source_doc_type: SourceDocType,
    source_doc_field: str,
    chunk_index: int,
    chunk_text: str,
    seed: int,
    oz: str | None = None,
) -> NewSimpleChunk:
    return NewSimpleChunk(
        project_uuid=project_uuid,
        source_doc_uuid=source_doc_uuid,
        source_doc_type=source_doc_type,
        source_doc_field=source_doc_field,
        source_doc_pages=[1],
        chunk_index=chunk_index,
        oz=oz,
        chunk_text=chunk_text,
        embedding=_make_vec(seed),
        embedding_model=settings.embedding_model,
    )


@dataclass
class Indexed:
    client: SearchClient
    es: AsyncElasticsearch
    index: str
    archive_index: str
    project_uuid: UUID
    lv_document_uuid: UUID
    prose_uuid: UUID
    lv_item_uuid: UUID
    prose_id: UUID
    lv_own_id: UUID
    lv_item_id: UUID


@pytest_asyncio.fixture
async def indexed() -> AsyncIterator[Indexed]:
    es = AsyncElasticsearch(
        settings.elasticsearch_url, node_class=NODE_CLASS, request_timeout=2
    )
    if not await es.ping():
        await es.close()
        pytest.skip(f"Elasticsearch unreachable at {settings.elasticsearch_url}")

    index = f"{settings.elasticsearch_index}_test_{uuid4().hex[:8]}"
    client = SearchClient(es, index=index)
    await client.ensure_index()

    project_uuid = uuid4()
    lv_document_uuid = uuid4()
    prose_uuid = uuid4()
    lv_item_uuid = uuid4()

    # Three chunks spanning the Simple/Plus distinctions: a prose DOCUMENT chunk, the LV
    # document's own DOCUMENT chunk (excluded by Plus), and a parsed LV_ITEM chunk.
    chunks = [
        _new_chunk(
            project_uuid=project_uuid,
            source_doc_uuid=prose_uuid,
            source_doc_type=SourceDocType.DOCUMENT,
            source_doc_field="sourcelines.line_text",
            chunk_index=0,
            chunk_text="Beton und Asphalt fuer die Strasse",
            seed=1,
        ),
        _new_chunk(
            project_uuid=project_uuid,
            source_doc_uuid=lv_document_uuid,
            source_doc_type=SourceDocType.DOCUMENT,
            source_doc_field="sourcelines.line_text",
            chunk_index=0,
            chunk_text="Beton Tragschicht im Leistungsverzeichnis",
            seed=2,
        ),
        _new_chunk(
            project_uuid=project_uuid,
            source_doc_uuid=lv_item_uuid,
            source_doc_type=SourceDocType.LV_ITEM,
            source_doc_field="lvitems.langtext_resolved",
            chunk_index=0,
            chunk_text="Beton Position Menge Einheit",
            seed=3,
            oz="01.0010",
        ),
    ]
    prose_id, lv_own_id, lv_item_id = await client.index_chunks(chunks, refresh=True)

    try:
        yield Indexed(
            client=client,
            es=es,
            index=index,
            archive_index=f"{index}_archive",
            project_uuid=project_uuid,
            lv_document_uuid=lv_document_uuid,
            prose_uuid=prose_uuid,
            lv_item_uuid=lv_item_uuid,
            prose_id=prose_id,
            lv_own_id=lv_own_id,
            lv_item_id=lv_item_id,
        )
    finally:
        await es.indices.delete(index=index, ignore_unavailable=True)
        await es.indices.delete(index=f"{index}_archive", ignore_unavailable=True)
        await client.close()


async def test_ensure_index_and_index_chunks(indexed: Indexed) -> None:
    assert await indexed.es.indices.exists(index=indexed.index)
    ids = {indexed.prose_id, indexed.lv_own_id, indexed.lv_item_id}
    assert len(ids) == 3
    assert all(isinstance(i, UUID) for i in ids)


async def test_simple_scope_returns_only_document_chunks(indexed: Indexed) -> None:
    scope = simple_filter(indexed.project_uuid)
    expected = {indexed.prose_id, indexed.lv_own_id}

    knn = await indexed.client.knn_search(_make_vec(1), scope, k=10)
    assert {sc.chunk.chunk_uuid for sc in knn} == expected

    bm25 = await indexed.client.lexical_search("beton", scope, size=10)
    assert {sc.chunk.chunk_uuid for sc in bm25} == expected


async def test_plus_scope_swaps_lv_document_for_lv_items(indexed: Indexed) -> None:
    scope = plus_filter(indexed.project_uuid, indexed.lv_document_uuid)
    expected = {indexed.prose_id, indexed.lv_item_id}

    knn = await indexed.client.knn_search(_make_vec(1), scope, k=10)
    assert {sc.chunk.chunk_uuid for sc in knn} == expected

    bm25 = await indexed.client.lexical_search("beton", scope, size=10)
    assert {sc.chunk.chunk_uuid for sc in bm25} == expected


async def test_archive_source_moves_chunks_and_stamps_archived_at(indexed: Indexed) -> None:
    moved = await indexed.client.archive_source(indexed.prose_uuid, SourceDocType.DOCUMENT)
    assert moved == 1

    # Gone from the live index.
    scope = simple_filter(indexed.project_uuid)
    live = await indexed.client.lexical_search("beton", scope, size=10)
    assert {sc.chunk.chunk_uuid for sc in live} == {indexed.lv_own_id}

    # Present in the archive index with an archived_at timestamp.
    archived = await indexed.es.search(
        index=indexed.archive_index,
        query={"term": {FIELD_SOURCE_DOC_UUID: str(indexed.prose_uuid)}},
    )
    hits = archived["hits"]["hits"]
    assert len(hits) == 1
    source = hits[0]["_source"]
    assert source[FIELD_CHUNK_TEXT] == "Beton und Asphalt fuer die Strasse"
    # Parses as an ISO-8601 timestamp.
    datetime.fromisoformat(source[FIELD_ARCHIVED_AT])


async def test_archive_and_delete_document_removes_lv_document_footprint(
    indexed: Indexed,
) -> None:
    # The LV document's own DOCUMENT chunk and its parsed LV_ITEM chunk go; the
    # unrelated prose chunk stays. The LV_ITEM chunk is keyed by lv_item_uuid, not the
    # document_uuid, so it is only matched because it is passed explicitly.
    removed = await indexed.client.archive_and_delete_document(
        indexed.project_uuid,
        indexed.lv_document_uuid,
        [indexed.lv_item_uuid],
    )
    assert removed == 2

    live = await indexed.es.search(index=indexed.index, query={"match_all": {}})
    live_ids = {hit["_id"] for hit in live["hits"]["hits"]}
    assert live_ids == {str(indexed.prose_id)}

    archived = await indexed.es.search(
        index=indexed.archive_index, query={"match_all": {}}
    )
    archived_hits = archived["hits"]["hits"]
    assert {hit["_id"] for hit in archived_hits} == {
        str(indexed.lv_own_id),
        str(indexed.lv_item_id),
    }
    for hit in archived_hits:
        datetime.fromisoformat(hit["_source"][FIELD_ARCHIVED_AT])


async def test_archive_and_delete_document_without_lv_items_keeps_other_chunks(
    indexed: Indexed,
) -> None:
    removed = await indexed.client.archive_and_delete_document(
        indexed.project_uuid, indexed.prose_uuid, []
    )
    assert removed == 1

    live = await indexed.es.search(index=indexed.index, query={"match_all": {}})
    live_ids = {hit["_id"] for hit in live["hits"]["hits"]}
    assert live_ids == {str(indexed.lv_own_id), str(indexed.lv_item_id)}
