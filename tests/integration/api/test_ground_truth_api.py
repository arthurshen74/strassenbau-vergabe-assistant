"""The eval-curation API: gold list (with staleness), upsert (validation + reconfirm), delete,
and the read-only corrections list + summary."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
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
from shared.models.enums import DocumentType, VariableCorrectionReason
from shared.models.ground_truth import NewVariableCorrection
from shared.models.lv_item import NewLVItem
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.variable_corrections import VariableCorrectionRepository
from shared.services.ground_truth import recipe_worklist_names

USER = UUID("00000000-0000-0000-0000-000000000001")
LK = "L_FRAESEN"


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
    lv_item_uuid: UUID


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
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv.pdf",
            number_of_pages=1,
        )
    )
    item = await LVItemRepository(conn).add(
        NewLVItem(
            document_uuid=document.document_uuid,
            oz="01.02.0030",
            kurztext="Asphalt fräsen",
            langtext="Asphalt fräsen, Tiefe 4 cm",
            menge=Decimal("100"),
            einheit="m2",
        )
    )
    return Fixture(project_uuid=project.project_uuid, lv_item_uuid=item.lv_item_uuid)


def _upsert_body(names: list[str]) -> dict:
    return {
        "leistung_key": LK,
        "bauverfahren_key": None,
        "gold_variables": {n: {"wert": "1", "art": "eingabe"} for n in names},
    }


async def test_gold_lifecycle(conn: AsyncConnection, client: AsyncClient) -> None:
    fx = await _fixture(conn, "VG-GTAPI")
    names = recipe_worklist_names(LK, None)
    assert names is not None
    base = f"/projects/{fx.project_uuid}/ground-truth"

    empty = await client.get(base)
    assert empty.status_code == 200
    assert empty.json() == []

    # Complete gold: upsert succeeds, oz comes from the LV item, row is not stale.
    put = await client.put(f"{base}/{fx.lv_item_uuid}", json=_upsert_body(names))
    assert put.status_code == 200
    body = put.json()
    assert body["oz"] == "01.02.0030"
    assert body["stale"] is False
    assert body["created_by_user_id"] == str(USER)

    # Subset gold: valid, but flagged stale with the missing names reported.
    put = await client.put(f"{base}/{fx.lv_item_uuid}", json=_upsert_body(names[1:]))
    assert put.status_code == 200
    body = put.json()
    assert body["stale"] is True
    assert names[0] in body["missing_variables"]

    listed = await client.get(base)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(f"{base}/{fx.lv_item_uuid}")
    assert deleted.status_code == 204
    assert (await client.delete(f"{base}/{fx.lv_item_uuid}")).status_code == 404


async def test_gold_upsert_validation(conn: AsyncConnection, client: AsyncClient) -> None:
    fx = await _fixture(conn, "VG-GTAPI-V")
    base = f"/projects/{fx.project_uuid}/ground-truth"

    # Variable not in the recipe worklist.
    bad_var = await client.put(
        f"{base}/{fx.lv_item_uuid}", json=_upsert_body(["erfundene_variable"])
    )
    assert bad_var.status_code == 422
    assert "erfundene_variable" in bad_var.json()["detail"]

    # Unknown recipe.
    bad_recipe = await client.put(
        f"{base}/{fx.lv_item_uuid}",
        json={"leistung_key": "l_gibt_es_nicht", "gold_variables": {}},
    )
    assert bad_recipe.status_code == 422

    # LV item from another project.
    other = await _fixture(conn, "VG-GTAPI-O")
    wrong_item = await client.put(
        f"{base}/{other.lv_item_uuid}", json=_upsert_body([])
    )
    assert wrong_item.status_code == 404

    # Unknown project is a 404 before any validation.
    assert (
        await client.get(f"/projects/{uuid4()}/ground-truth")
    ).status_code == 404


async def test_corrections_read_only_endpoints(
    conn: AsyncConnection, client: AsyncClient
) -> None:
    fx = await _fixture(conn, "VG-GTAPI-C")
    await VariableCorrectionRepository(conn).add_many(
        [
            NewVariableCorrection(
                project_uuid=fx.project_uuid,
                variable_name="tiefe_cm",
                final_wert="4",
                reason=VariableCorrectionReason.FALSCHER_WERT,
                created_by_user_id=USER,
            ),
            NewVariableCorrection(
                project_uuid=fx.project_uuid,
                variable_name="laenge_m",
                final_wert="1240",
                created_by_user_id=USER,
            ),
        ]
    )
    base = f"/projects/{fx.project_uuid}/corrections"

    listed = await client.get(base)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    filtered = await client.get(base, params={"reason": "falscher_wert"})
    assert filtered.status_code == 200
    assert [c["variable_name"] for c in filtered.json()] == ["tiefe_cm"]

    summary = await client.get(f"{base}/summary")
    assert summary.status_code == 200
    rows = {(r["variable_name"], r["reason"]): r["count"] for r in summary.json()}
    assert rows == {("tiefe_cm", "falscher_wert"): 1, ("laenge_m", None): 1}
