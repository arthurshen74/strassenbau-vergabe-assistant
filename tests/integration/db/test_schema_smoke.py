"""End-to-end DDL smoke test against real Postgres.

Proves the Wave 2A schema builds (conftest create_all) and that the non-trivial
constraints actually fire: the document_type / status CHECKs and the
(document_uuid, oz) composite unique. Several LV documents per project are allowed.
Uses Core directly (no repositories) so it validates the tables alone.
"""

from __future__ import annotations

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.lv_items import lv_items
from shared.db.tables.projects import projects
from shared.models.enums import DocumentType, IngestStatus


async def _make_project(conn: AsyncConnection) -> object:
    return (
        await conn.execute(
            insert(projects)
            .values(
                vergabe_id="VG-1",
                project_name="A1",
                project_description="d",
                vergabestelle="B",
            )
            .returning(projects.c.project_uuid)
        )
    ).scalar_one()


async def _add_document(
    conn: AsyncConnection, project_uuid: object, document_type: str, file_name: str
) -> object:
    return (
        await conn.execute(
            insert(documents)
            .values(
                project_uuid=project_uuid,
                document_type=document_type,
                file_name=file_name,
                number_of_pages=1,
            )
            .returning(documents.c.document_uuid)
        )
    ).scalar_one()


async def test_project_round_trips(conn: AsyncConnection) -> None:
    pid = await _make_project(conn)
    name = (
        await conn.execute(
            select(projects.c.project_name).where(projects.c.project_uuid == pid)
        )
    ).scalar_one()
    assert name == "A1"


async def test_several_lv_documents_per_project_allowed(conn: AsyncConnection) -> None:
    pid = await _make_project(conn)
    await _add_document(conn, pid, DocumentType.LV_DOCUMENT.value, "lv1.x83")
    await _add_document(conn, pid, DocumentType.LV_DOCUMENT.value, "lv2.d83")
    rows = await conn.execute(
        select(documents.c.document_uuid).where(
            documents.c.project_uuid == pid,
            documents.c.document_type == DocumentType.LV_DOCUMENT.value,
        )
    )
    assert len(rows.all()) == 2


async def test_document_type_check_constraint(conn: AsyncConnection) -> None:
    pid = await _make_project(conn)
    with pytest.raises(IntegrityError):
        await _add_document(conn, pid, "BOGUS_TYPE", "x.pdf")


async def test_lv_item_oz_unique_per_document(conn: AsyncConnection) -> None:
    pid = await _make_project(conn)
    did = await _add_document(conn, pid, DocumentType.LV_DOCUMENT.value, "lv.pdf")
    values = dict(
        document_uuid=did, oz="01.0010", kurztext="k", langtext="l", menge=1, einheit="m"
    )
    await conn.execute(insert(lv_items).values(**values))
    with pytest.raises(IntegrityError):
        await conn.execute(insert(lv_items).values(**values))


async def test_ingest_job_status_check(conn: AsyncConnection) -> None:
    pid = await _make_project(conn)
    did = await _add_document(conn, pid, DocumentType.PROSE_DOCUMENT.value, "p.pdf")
    await conn.execute(
        insert(ingest_jobs).values(document_uuid=did, status=IngestStatus.RUNNING.value)
    )
    with pytest.raises(IntegrityError):
        await conn.execute(insert(ingest_jobs).values(document_uuid=did, status="nope"))
