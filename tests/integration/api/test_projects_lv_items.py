from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app
from shared.db.tables.documents import documents
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, LVTextKind
from shared.models.lv_item import NewLVItem
from shared.models.lv_text import NewLVText
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.lv_texts import LVTextRepository
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


def _text(document_uuid: UUID, sequence: int) -> NewLVText:
    return NewLVText(
        document_uuid=document_uuid,
        kind=LVTextKind.REMARK,
        index=sequence,
        sequence=sequence,
        body=f"hinweis {sequence}",
    )


async def _add_second_lv_document(
    conn: AsyncConnection, project_uuid: UUID, first_lv: UUID
) -> UUID:
    """A second LV document created after `first_lv`."""
    second = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project_uuid,
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv2.d83",
            number_of_pages=0,
        )
    )
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for document_uuid, created_at in (
        (first_lv, base),
        (second.document_uuid, base + timedelta(minutes=1)),
    ):
        await conn.execute(
            update(documents)
            .where(documents.c.document_uuid == document_uuid)
            .values(created_at=created_at)
        )
    return second.document_uuid


async def test_project_lv_listings_span_two_lv_documents_in_document_order(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project_uuid, lv_doc, _ = await _project_with_lv_document(conn)
    second = await _add_second_lv_document(conn, project_uuid, lv_doc)
    await LVItemRepository(conn).add_many(
        [_item(second, "01.0010"), _item(lv_doc, "02.0010"), _item(lv_doc, "01.0010")]
    )
    texts = LVTextRepository(conn)
    await texts.replace(second, [_text(second, 0)])
    await texts.replace(lv_doc, [_text(lv_doc, 1), _text(lv_doc, 0)])

    items = (await client.get(f"/projects/{project_uuid}/lv-items")).json()
    lv_texts = (await client.get(f"/projects/{project_uuid}/lv-texts")).json()

    assert [(i["document_uuid"], i["oz"]) for i in items] == [
        (str(lv_doc), "01.0010"),
        (str(lv_doc), "02.0010"),
        (str(second), "01.0010"),
    ]
    assert [(t["document_uuid"], t["sequence"]) for t in lv_texts] == [
        (str(lv_doc), 0),
        (str(lv_doc), 1),
        (str(second), 0),
    ]


async def test_document_lv_routes_return_only_that_document(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project_uuid, lv_doc, _ = await _project_with_lv_document(conn)
    second = await _add_second_lv_document(conn, project_uuid, lv_doc)
    await LVItemRepository(conn).add_many(
        [_item(lv_doc, "01.0010"), _item(second, "01.0010"), _item(second, "01.0020")]
    )
    await LVTextRepository(conn).replace(second, [_text(second, 0)])

    base = f"/projects/{project_uuid}/documents/{second}"
    items = await client.get(f"{base}/lv-items")
    lv_texts = await client.get(f"{base}/lv-texts")

    assert items.status_code == 200
    assert [(i["document_uuid"], i["oz"]) for i in items.json()] == [
        (str(second), "01.0010"),
        (str(second), "01.0020"),
    ]
    assert lv_texts.status_code == 200
    assert [t["body"] for t in lv_texts.json()] == ["hinweis 0"]


async def test_document_lv_routes_empty_for_prose_document(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project_uuid, _, prose_doc = await _project_with_lv_document(conn)
    base = f"/projects/{project_uuid}/documents/{prose_doc}"
    for suffix in ("lv-items", "lv-texts"):
        resp = await client.get(f"{base}/{suffix}")
        assert resp.status_code == 200
        assert resp.json() == []


async def test_document_lv_routes_404_outside_project(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project_uuid, _, _ = await _project_with_lv_document(conn)
    other_project, other_lv, _ = await _project_with_lv_document(conn)
    for document_uuid in (other_lv, uuid4()):
        base = f"/projects/{project_uuid}/documents/{document_uuid}"
        for suffix in ("lv-items", "lv-texts"):
            resp = await client.get(f"{base}/{suffix}")
            assert resp.status_code == 404
