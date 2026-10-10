"""GET /projects/{project}/documents/{document}/form-fields.

The route reads through the engine (its own connection), so data is committed via the
engine and the project is deleted afterwards (everything cascades from it)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine, get_search
from api.main import app
from shared.db.tables.projects import projects
from shared.db.unit_of_work import unit_of_work
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, FormRole
from shared.models.form_field import NewFormField
from shared.models.project import NewProject


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_engine] = lambda: engine
    # The detail service holds a SearchClient; listing form fields never touches it.
    app.dependency_overrides[get_search] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded(engine: AsyncEngine) -> AsyncIterator[dict[str, UUID]]:
    """A project with one form (two fields) and one prose document."""
    async with unit_of_work(engine) as uow:
        project = await uow.projects.add(NewProject(project_name="Form API"))
        form = await uow.documents.add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.FORM_DOCUMENT,
                file_name="T1.1 FB 312-B.pdf",
                number_of_pages=1,
                form_role=FormRole.VERGABESTELLE,
                form_id="FB 312-B",
            )
        )
        prose = await uow.documents.add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.PROSE_DOCUMENT,
                file_name="Plan.pdf",
                number_of_pages=1,
            )
        )
        await uow.form_fields.add_many(
            [
                NewFormField(
                    document_uuid=form.document_uuid,
                    field_order=order,
                    section="Kopf",
                    name=name,
                    label=label,
                    value=value,
                    page=1,
                )
                for order, (name, label, value) in enumerate(
                    [("VE_VNR", "Vergabenummer", "26/001"), ("VE_X", None, "ja")]
                )
            ]
        )
    yield {
        "project": project.project_uuid,
        "form": form.document_uuid,
        "prose": prose.document_uuid,
    }
    async with engine.begin() as conn:
        await conn.execute(
            delete(projects).where(projects.c.project_uuid == project.project_uuid)
        )


async def test_lists_form_fields_in_order(
    client: AsyncClient, seeded: dict[str, UUID]
) -> None:
    resp = await client.get(
        f"/projects/{seeded['project']}/documents/{seeded['form']}/form-fields"
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == [
        {
            "field_order": 0,
            "section": "Kopf",
            "name": "VE_VNR",
            "label": "Vergabenummer",
            "value": "26/001",
            "page": 1,
        },
        {
            "field_order": 1,
            "section": "Kopf",
            "name": "VE_X",
            "label": None,
            "value": "ja",
            "page": 1,
        },
    ]


async def test_non_form_and_foreign_documents_are_404(
    client: AsyncClient, seeded: dict[str, UUID]
) -> None:
    prose = await client.get(
        f"/projects/{seeded['project']}/documents/{seeded['prose']}/form-fields"
    )
    foreign = await client.get(
        f"/projects/{uuid4()}/documents/{seeded['form']}/form-fields"
    )

    assert prose.status_code == 404
    assert foreign.status_code == 404
