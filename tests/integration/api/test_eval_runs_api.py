"""The eval-runs API: enqueue validation (supported kinds, project scoping), list/detail,
and the events/results reads."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

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
from shared.models.project import NewProject
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


async def test_enqueue_and_read(conn: AsyncConnection, client: AsyncClient) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-ER", project_name="P", project_description="d", vergabestelle="V"
        )
    )

    created = await client.post(
        "/eval-runs",
        json={
            "kind": "calculator_gold",
            "project_uuid": str(project.project_uuid),
            "params": {"abs_tol": "0.01"},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "queued"
    assert body["params"] == {"abs_tol": "0.01"}
    run_uuid = body["eval_run_uuid"]

    detail = await client.get(f"/eval-runs/{run_uuid}")
    assert detail.status_code == 200

    listed = await client.get("/eval-runs", params={"project_uuid": str(project.project_uuid)})
    assert [r["eval_run_uuid"] for r in listed.json()] == [run_uuid]

    events = await client.get(f"/eval-runs/{run_uuid}/events")
    assert events.status_code == 200 and events.json() == []
    results = await client.get(f"/eval-runs/{run_uuid}/results")
    assert results.status_code == 200 and results.json() == []


async def test_enqueue_validation(client: AsyncClient) -> None:
    # rag kinds exist in the enum but are not implemented yet.
    not_impl = await client.post("/eval-runs", json={"kind": "rag_retrieval"})
    assert not_impl.status_code == 422
    assert "not implemented" in not_impl.json()["detail"]

    # calculator_gold is project-bound.
    no_project = await client.post("/eval-runs", json={"kind": "calculator_gold"})
    assert no_project.status_code == 422
    assert "requires a project_uuid" in no_project.json()["detail"]

    unknown_project = await client.post(
        "/eval-runs",
        json={"kind": "calculator_gold", "project_uuid": str(uuid4())},
    )
    assert unknown_project.status_code == 422

    # chat_values needs no project.
    ok = await client.post("/eval-runs", json={"kind": "chat_values"})
    assert ok.status_code == 201

    assert (await client.get(f"/eval-runs/{uuid4()}")).status_code == 404
