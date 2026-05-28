from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.project_document_type import (
    FormTypeStandard,
    NewProjectDocumentType,
)
from shared.repositories.project_document_types import (
    ProjectDocumentTypeRepository,
)


async def test_get_by_type_returns_added_row(conn: AsyncConnection) -> None:
    repo = ProjectDocumentTypeRepository(conn)
    created = await repo.add(
        NewProjectDocumentType(
            document_type="LV",
            document_type_description="Bill of Quantities (BoQ)",
        )
    )
    fetched = await repo.get_by_type("LV")
    assert fetched is not None
    assert fetched.document_type_uuid == created.document_type_uuid


async def test_get_by_type_missing_returns_none(conn: AsyncConnection) -> None:
    repo = ProjectDocumentTypeRepository(conn)
    assert await repo.get_by_type("DOES_NOT_EXIST") is None


async def test_unique_document_type_blocks_duplicate(conn: AsyncConnection) -> None:
    repo = ProjectDocumentTypeRepository(conn)
    await repo.add(NewProjectDocumentType(document_type="LV"))
    with pytest.raises(IntegrityError):
        await repo.add(NewProjectDocumentType(document_type="LV"))


async def test_form_type_standard_accepts_valid_values(
    conn: AsyncConnection,
) -> None:
    repo = ProjectDocumentTypeRepository(conn)
    a = await repo.add(
        NewProjectDocumentType(
            document_type="HVA",
            form_type_standard=FormTypeStandard.HVA_STB,
            form_type_number=211,
        )
    )
    b = await repo.add(
        NewProjectDocumentType(
            document_type="VHB_DOC",
            form_type_standard=FormTypeStandard.VHB,
        )
    )
    assert a.form_type_standard == FormTypeStandard.HVA_STB
    assert b.form_type_standard == FormTypeStandard.VHB


async def test_form_type_standard_allows_null(conn: AsyncConnection) -> None:
    repo = ProjectDocumentTypeRepository(conn)
    created = await repo.add(NewProjectDocumentType(document_type="TB"))
    assert created.form_type_standard is None
    assert created.form_type_number is None


async def test_form_type_standard_check_rejects_unknown_value(
    conn: AsyncConnection,
) -> None:
    from sqlalchemy import insert

    from shared.db.tables.project_document_types import project_document_types

    with pytest.raises(IntegrityError):
        await conn.execute(
            insert(project_document_types).values(
                document_type="BAD",
                form_type_standard="NOT_A_STANDARD",
            )
        )
