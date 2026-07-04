"""The RAG reference-question API: lifecycle (create/list/update/delete), ref validation
against the project's documents, and project scoping."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import (
    get_connection,
    get_embeddings,
    get_engine,
    get_llm_client,
    get_reranker,
    get_search,
    get_uow,
)
from api.main import app
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.projects import ProjectRepository


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _connection() -> AsyncIterator[AsyncConnection]:
        yield conn

    async def _uow() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    app.dependency_overrides[get_connection] = _connection
    app.dependency_overrides[get_uow] = _uow
    for dep in (get_engine, get_llm_client, get_embeddings, get_search, get_reranker):
        app.dependency_overrides[dep] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@dataclass
class Fixture:
    project_uuid: UUID
    document_uuid: UUID


async def _fixture(conn: AsyncConnection, vergabe_id: str) -> Fixture:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id=vergabe_id,
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    document = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="baubeschreibung.pdf",
            number_of_pages=20,
        )
    )
    return Fixture(project_uuid=project.project_uuid, document_uuid=document.document_uuid)


def _body(fx: Fixture, refs: list[dict] | None = None) -> dict:
    return {
        "question": "Wie viele Streckenabschnitte umfasst die Maßnahme?",
        "gold_answer": "4 (SA 1 - SA 4)",
        "refs": refs if refs is not None else [],
        "question_type": "aggregation",
        "category": "kalkulator",
    }


async def test_lifecycle(conn: AsyncConnection, client: AsyncClient) -> None:
    fx = await _fixture(conn, "VG-RAGAPI")
    base = f"/projects/{fx.project_uuid}/rag-ground-truth"

    assert (await client.get(base)).json() == []

    created = await client.post(
        base, json=_body(fx, refs=[{"document_uuid": str(fx.document_uuid), "page": 7}])
    )
    assert created.status_code == 201
    body = created.json()
    assert body["refs_missing"] is False
    rag_uuid = body["rag_ground_truth_uuid"]

    # No refs: legal, but flagged.
    no_refs = await client.post(base, json=_body(fx))
    assert no_refs.status_code == 201
    assert no_refs.json()["refs_missing"] is True

    listed = await client.get(base)
    assert len(listed.json()) == 2

    updated = await client.put(
        f"{base}/{rag_uuid}",
        json={**_body(fx), "gold_answer": "4 Streckenabschnitte (SA 1 - SA 4)"},
    )
    assert updated.status_code == 200
    assert updated.json()["gold_answer"] == "4 Streckenabschnitte (SA 1 - SA 4)"

    assert (await client.delete(f"{base}/{rag_uuid}")).status_code == 204
    assert (await client.delete(f"{base}/{rag_uuid}")).status_code == 404


async def test_ref_validation(conn: AsyncConnection, client: AsyncClient) -> None:
    fx = await _fixture(conn, "VG-RAGAPI-V")
    base = f"/projects/{fx.project_uuid}/rag-ground-truth"

    foreign = await client.post(
        base, json=_body(fx, refs=[{"document_uuid": str(uuid4()), "page": 1}])
    )
    assert foreign.status_code == 422

    beyond = await client.post(
        base, json=_body(fx, refs=[{"document_uuid": str(fx.document_uuid), "page": 21}])
    )
    assert beyond.status_code == 422
    assert "baubeschreibung.pdf" in beyond.json()["detail"]

    # Unknown enum value is rejected by the schema.
    bad_type = await client.post(base, json={**_body(fx), "question_type": "raten"})
    assert bad_type.status_code == 422


async def test_project_scoping(conn: AsyncConnection, client: AsyncClient) -> None:
    fx = await _fixture(conn, "VG-RAGAPI-S")
    other = await _fixture(conn, "VG-RAGAPI-S2")
    base = f"/projects/{fx.project_uuid}/rag-ground-truth"

    created = await client.post(base, json=_body(fx))
    rag_uuid = created.json()["rag_ground_truth_uuid"]

    # The row is not reachable through another project.
    wrong = await client.put(
        f"/projects/{other.project_uuid}/rag-ground-truth/{rag_uuid}",
        json=_body(other),
    )
    assert wrong.status_code == 404
    assert (await client.get(f"/projects/{uuid4()}/rag-ground-truth")).status_code == 404
