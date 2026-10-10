from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType, LVTextKind, LVTextPlacement
from shared.models.lv_text import NewLVText
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_texts import LVTextRepository
from shared.repositories.projects import ProjectRepository


async def _lv_document(conn: AsyncConnection) -> tuple[UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-LVT",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    lv = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv.x83",
            number_of_pages=0,
        )
    )
    return project.project_uuid, lv.document_uuid


def _vortext(document_uuid: UUID, sequence: int) -> NewLVText:
    return NewLVText(
        document_uuid=document_uuid,
        kind=LVTextKind.ADD_TEXT,
        placement=LVTextPlacement.BEFORE_BOQ,
        index=sequence,
        sequence=sequence,
        heading="Vorbemerkungen",
        body=f"Block {sequence}.",
    )


def _remark(document_uuid: UUID, sequence: int, parent_oz: str | None) -> NewLVText:
    return NewLVText(
        document_uuid=document_uuid,
        kind=LVTextKind.REMARK,
        parent_oz=parent_oz,
        index=0,
        sequence=sequence,
        body=f"Hinweis {sequence}.",
    )


async def test_replace_inserts_in_sequence_and_lists_by_document_and_project(
    conn: AsyncConnection,
) -> None:
    repo = LVTextRepository(conn)
    project_uuid, document_uuid = await _lv_document(conn)

    created, removed = await repo.replace(
        document_uuid,
        [
            _vortext(document_uuid, 0),
            _remark(document_uuid, 1, None),
            _remark(document_uuid, 2, "01"),
        ],
    )
    assert removed == []
    assert [t.sequence for t in created] == [0, 1, 2]
    assert created[0].kind is LVTextKind.ADD_TEXT
    assert created[0].placement is LVTextPlacement.BEFORE_BOQ
    assert created[2].parent_oz == "01"

    by_document = await repo.list_by_document(document_uuid)
    assert [t.lv_text_uuid for t in by_document] == [t.lv_text_uuid for t in created]
    by_project = await repo.list_by_project(project_uuid)
    assert [t.body for t in by_project] == ["Block 0.", "Hinweis 1.", "Hinweis 2."]
    assert set(await repo.list_uuids_by_document(document_uuid)) == {
        t.lv_text_uuid for t in created
    }


async def test_replace_removes_prior_rows_and_returns_their_uuids(
    conn: AsyncConnection,
) -> None:
    repo = LVTextRepository(conn)
    _, document_uuid = await _lv_document(conn)
    first, _ = await repo.replace(document_uuid, [_vortext(document_uuid, 0)])

    second, removed = await repo.replace(
        document_uuid, [_remark(document_uuid, 0, None)]
    )

    assert removed == [first[0].lv_text_uuid]
    assert [t.kind for t in await repo.list_by_document(document_uuid)] == [
        LVTextKind.REMARK
    ]
    assert second[0].lv_text_uuid != first[0].lv_text_uuid

    _, removed_all = await repo.replace(document_uuid, [])
    assert removed_all == [second[0].lv_text_uuid]
    assert await repo.list_by_document(document_uuid) == []
