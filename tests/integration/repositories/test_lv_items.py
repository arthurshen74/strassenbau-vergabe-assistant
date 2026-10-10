from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.lv_item import NewLVItem
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository


@dataclass
class Fixture:
    project_uuid: UUID
    lv_document_uuid: UUID
    prose_document_uuid: UUID


async def _fixture(conn: AsyncConnection) -> Fixture:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-LV",
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
    return Fixture(project.project_uuid, lv.document_uuid, prose.document_uuid)


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


async def test_add_and_get(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    created = await repo.add(_item(fx.lv_document_uuid, "01.0010"))
    fetched = await repo.get(created.lv_item_uuid)
    assert fetched is not None
    assert fetched.oz == "01.0010"
    assert fetched.menge == Decimal("1.0000")


async def test_get_by_project_and_oz_resolves_through_lv_document(
    conn: AsyncConnection,
) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    lv_item = await repo.add(_item(fx.lv_document_uuid, "02.0020"))
    # A same-oz item on a non-LV document must not shadow the LV one.
    await repo.add(_item(fx.prose_document_uuid, "02.0020"))

    found = await repo.get_by_project_and_oz(fx.project_uuid, "02.0020")
    assert found is not None
    assert found.lv_item_uuid == lv_item.lv_item_uuid
    assert found.document_uuid == fx.lv_document_uuid


async def test_get_by_project_and_oz_missing(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    assert await repo.get_by_project_and_oz(fx.project_uuid, "99.9999") is None


async def test_list_by_parent_oz_resolves_through_lv_document(
    conn: AsyncConnection,
) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    await repo.add_many(
        [
            _item(fx.lv_document_uuid, "01.0030", parent_oz="01"),
            _item(fx.lv_document_uuid, "01.0010", parent_oz="01"),
            _item(fx.lv_document_uuid, "01.0020", parent_oz="01"),
            _item(fx.lv_document_uuid, "02.0010", parent_oz="02"),
        ]
    )
    # A child under the same parent_oz but on a non-LV document is excluded.
    await repo.add(_item(fx.prose_document_uuid, "01.0040", parent_oz="01"))

    children = await repo.list_by_parent_oz(fx.project_uuid, "01")
    assert [c.oz for c in children] == ["01.0010", "01.0020", "01.0030"]


async def test_add_many_returns_all(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    created = await repo.add_many(
        [_item(fx.lv_document_uuid, f"03.{i:04d}") for i in range(1, 4)]
    )
    assert len(created) == 3
    assert {c.oz for c in created} == {"03.0001", "03.0002", "03.0003"}
    assert await repo.add_many([]) == []


async def test_add_many_upserts_on_natural_key(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    first = await repo.add_many([_item(fx.lv_document_uuid, "04.0010")])

    # Re-ingest the same oz with changed content: it updates in place, keeping the uuid.
    again = await repo.add_many(
        [
            NewLVItem(
                document_uuid=fx.lv_document_uuid,
                oz="04.0010",
                kurztext="updated kurz",
                langtext="updated lang",
                menge=Decimal("9.0000"),
                einheit="St",
            )
        ]
    )

    assert again[0].lv_item_uuid == first[0].lv_item_uuid
    assert await repo.list_by_project(fx.project_uuid) == again  # exactly one row
    refetched = await repo.get(first[0].lv_item_uuid)
    assert refetched is not None
    assert refetched.kurztext == "updated kurz" and refetched.menge == Decimal("9.0000")


async def test_delete_missing_removes_absent_ozs(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    created = await repo.add_many(
        [_item(fx.lv_document_uuid, oz) for oz in ("05.0010", "05.0020", "05.0030")]
    )
    by_oz = {c.oz: c.lv_item_uuid for c in created}

    removed = await repo.delete_missing(fx.lv_document_uuid, ["05.0010"])

    assert set(removed) == {by_oz["05.0020"], by_oz["05.0030"]}
    remaining = await repo.list_by_project(fx.project_uuid)
    assert [r.oz for r in remaining] == ["05.0010"]


async def test_delete_missing_empty_keep_removes_all(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    await repo.add_many([_item(fx.lv_document_uuid, oz) for oz in ("06.0010", "06.0020")])

    removed = await repo.delete_missing(fx.lv_document_uuid, [])

    assert len(removed) == 2
    assert await repo.list_by_project(fx.project_uuid) == []


async def _second_lv_document(conn: AsyncConnection, fx: Fixture) -> UUID:
    """A second LV document created after the fixture's one."""
    second = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=fx.project_uuid,
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv2.d83",
            number_of_pages=0,
        )
    )
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for document_uuid, created_at in (
        (fx.lv_document_uuid, base),
        (second.document_uuid, base + timedelta(minutes=1)),
    ):
        await conn.execute(
            update(documents)
            .where(documents.c.document_uuid == document_uuid)
            .values(created_at=created_at)
        )
    return second.document_uuid


async def test_list_by_project_groups_by_document(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    second = await _second_lv_document(conn, fx)
    await repo.add_many([_item(second, "01.0010"), _item(second, "02.0010")])
    await repo.add_many(
        [_item(fx.lv_document_uuid, "03.0010"), _item(fx.lv_document_uuid, "01.0020")]
    )

    listed = await repo.list_by_project(fx.project_uuid)

    assert [(i.document_uuid, i.oz) for i in listed] == [
        (fx.lv_document_uuid, "01.0020"),
        (fx.lv_document_uuid, "03.0010"),
        (second, "01.0010"),
        (second, "02.0010"),
    ]


async def test_list_by_project_and_oz_returns_every_match(
    conn: AsyncConnection,
) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    second = await _second_lv_document(conn, fx)
    await repo.add(_item(second, "01.0010"))
    await repo.add(_item(fx.lv_document_uuid, "01.0010"))

    matches = await repo.list_by_project_and_oz(fx.project_uuid, "01.0010")
    first = await repo.get_by_project_and_oz(fx.project_uuid, "01.0010")

    assert [m.document_uuid for m in matches] == [fx.lv_document_uuid, second]
    assert first is not None
    assert first.document_uuid == fx.lv_document_uuid


async def test_list_by_document_only_that_document(conn: AsyncConnection) -> None:
    repo = LVItemRepository(conn)
    fx = await _fixture(conn)
    second = await _second_lv_document(conn, fx)
    await repo.add_many(
        [_item(fx.lv_document_uuid, "02.0010"), _item(fx.lv_document_uuid, "01.0010")]
    )
    await repo.add(_item(second, "01.0010"))

    listed = await repo.list_by_document(fx.lv_document_uuid)

    assert [(i.document_uuid, i.oz) for i in listed] == [
        (fx.lv_document_uuid, "01.0010"),
        (fx.lv_document_uuid, "02.0010"),
    ]
    assert await repo.list_by_document(fx.prose_document_uuid) == []
