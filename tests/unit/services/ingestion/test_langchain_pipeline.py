from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.documents import Document

from shared.services.ingestion import langchain_pipeline as lp


class _FakeStore:
    def __init__(self) -> None:
        self.added: list[tuple[list[tuple[str, list[float]]], list[dict] | None]] = []

    def add_embeddings(
        self, text_embeddings: Any, metadatas: list[dict] | None = None
    ) -> list[str]:
        pairs = list(text_embeddings)
        self.added.append((pairs, metadatas))
        return [f"id-{i}" for i in range(len(pairs))]


class _FakeESClient:
    def __init__(self) -> None:
        self.deleted: list[dict] = []

    def delete_by_query(self, **kwargs: Any) -> None:
        self.deleted.append(kwargs)

    def close(self) -> None:
        pass


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Any, Any]] = []

    async def embed(
        self, texts: list[str], *, project_uuid: Any = None, ingest_job_uuid: Any = None
    ) -> list[list[float]]:
        self.calls.append((texts, project_uuid, ingest_job_uuid))
        return [[float(i), float(i)] for i in range(len(texts))]


@pytest.fixture
def ingestor(monkeypatch: pytest.MonkeyPatch):
    store = _FakeStore()
    monkeypatch.setattr(lp, "build_elasticsearch_client", _FakeESClient)
    monkeypatch.setattr(lp, "build_langchain_embeddings", lambda: object())
    monkeypatch.setattr(lp, "build_langchain_vector_store", lambda emb, client: store)
    embeddings = _FakeEmbeddings()
    return lp.LangchainIngestor(embeddings), embeddings, store


async def test_ingest_embeds_with_ids_then_writes_precomputed_vectors(
    ingestor, monkeypatch: pytest.MonkeyPatch
) -> None:
    ing, embeddings, store = ingestor
    document_uuid, project_uuid, job_uuid = uuid4(), uuid4(), uuid4()
    chunks = [
        Document(page_content="a", metadata={"k": 1}),
        Document(page_content="b", metadata={"k": 2}),
    ]
    monkeypatch.setattr(ing, "_load_and_split", lambda d, p, b: chunks)

    count = await ing.ingest(document_uuid, project_uuid, b"%PDF", ingest_job_uuid=job_uuid)

    assert count == 2
    # Embedding goes through the first-party client with the project + ingest-job ids.
    assert embeddings.calls == [(["a", "b"], project_uuid, job_uuid)]
    # Prior vectors are deleted before the write.
    assert len(ing._client.deleted) == 1
    # Precomputed vectors (not re-embedded) are indexed with the chunk metadata.
    (pairs, metadatas) = store.added[0]
    assert pairs == [("a", [0.0, 0.0]), ("b", [1.0, 1.0])]
    assert metadatas == [{"k": 1}, {"k": 2}]


async def test_empty_pdf_short_circuits(ingestor, monkeypatch: pytest.MonkeyPatch) -> None:
    ing, embeddings, store = ingestor
    monkeypatch.setattr(ing, "_load_and_split", lambda d, p, b: [])

    count = await ing.ingest(uuid4(), uuid4(), b"%PDF")

    assert count == 0
    assert embeddings.calls == []
    assert store.added == []
    assert ing._client.deleted == []
