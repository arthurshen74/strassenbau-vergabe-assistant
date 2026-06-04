from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.lv_item import NewLVItem
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """AsyncClient whose reads/writes run on the per-test connection, so every change
    rolls back with the `conn` fixture and tests stay isolated."""

    async def _connection() -> AsyncIterator[AsyncConnection]:
        yield conn

    async def _uow() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    app.dependency_overrides[get_connection] = _connection
    app.dependency_overrides[get_uow] = _uow
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def _project_with_lv_document(conn: AsyncConnection) -> tuple[UUID, UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-LV-API",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    docs = DocumentRepository(conn)
    lv = await docs.add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv.pdf",
            number_of_pages=1,
        )
    )
    prose = await docs.add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="prose.pdf",
            number_of_pages=1,
        )
    )
    return project.project_uuid, lv.document_uuid, prose.document_uuid


def _item(document_uuid: UUID, oz: str, **kw: object) -> NewLVItem:
    return NewLVItem(
        document_uuid=document_uuid,
        oz=oz,
        kurztext=f"kurz {oz}",
        langtext=f"lang {oz}",
        menge=Decimal("1.0000"),
        einheit="m",
        **kw,
    )


async def test_list_lv_items_returns_lv_document_items_ordered(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project_uuid, lv_doc, prose_doc = await _project_with_lv_document(conn)
    await LVItemRepository(conn).add_many(
        [
            _item(lv_doc, "01.0020", stl_nr="STL-9", hinweis="careful"),
            _item(lv_doc, "01.0010"),
        ]
    )
    # An item on the prose document must not be returned by the LV listing.
    await LVItemRepository(conn).add(_item(prose_doc, "99.9999"))

    resp = await client.get(f"/projects/{project_uuid}/lv-items")

    assert resp.status_code == 200
    body = resp.json()
    assert [i["oz"] for i in body] == ["01.0010", "01.0020"]
    detailed = body[1]
    assert detailed["kurztext"] == "kurz 01.0020"
    assert detailed["stl_nr"] == "STL-9"
    assert detailed["hinweis"] == "careful"
    assert detailed["einheit"] == "m"


async def test_list_lv_items_empty_for_project_without_lv(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-EMPTY",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    resp = await client.get(f"/projects/{project.project_uuid}/lv-items")
    assert resp.status_code == 200
    assert resp.json() == []
