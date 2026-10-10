from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

import shared.services.project_service as project_service
from api.deps import get_connection, get_storage, get_uow
from api.main import app
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import DocumentType, IngestStatus
from shared.models.project import NewProject
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _connection() -> AsyncIterator[AsyncConnection]:
        yield conn

    async def _uow() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    app.dependency_overrides[get_connection] = _connection
    app.dependency_overrides[get_uow] = _uow
    # The writable service wants a StorageClient, which create/update never touch.
    app.dependency_overrides[get_storage] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def test_create_with_name_only(client: AsyncClient) -> None:
    resp = await client.post("/projects", json={"project_name": "B247 OD"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project_name"] == "B247 OD"
    assert body["vergabe_id"] is None
    assert body["massnahmenummer"] is None
    assert body["bauleistung"] is None


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    resp = await client.post("/projects", json={"project_name": ""})
    assert resp.status_code == 422


async def test_patch_updates_only_sent_fields(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(project_name="P", vergabe_id="VG-1", vergabestelle="LRA")
    )
    resp = await client.patch(
        f"/projects/{project.project_uuid}",
        json={"massnahmenummer": "M-1", "bauleistung": "Deckenerneuerung"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["massnahmenummer"] == "M-1"
    assert body["bauleistung"] == "Deckenerneuerung"
    assert body["vergabe_id"] == "VG-1"
    assert body["vergabestelle"] == "LRA"


async def test_patch_null_clears_field(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(project_name="P", location="Erfurt")
    )
    resp = await client.patch(
        f"/projects/{project.project_uuid}", json={"location": None}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["location"] is None


async def test_patch_rejects_empty_name_and_unknown_field(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    url = f"/projects/{project.project_uuid}"
    assert (await client.patch(url, json={"project_name": ""})).status_code == 422
    assert (await client.patch(url, json={"surprise": "x"})).status_code == 422


async def test_patch_missing_project_is_404(client: AsyncClient) -> None:
    resp = await client.patch(f"/projects/{uuid4()}", json={"location": "x"})
    assert resp.status_code == 404


class _RecordingStorage:
    def __init__(self) -> None:
        self.put: list[str] = []

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.put.append(key)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


async def test_create_from_zip_ingests_nested_files(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    storage = _RecordingStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    nested = _zip({"Los2.d83": b"d83", "notes.txt": b"n"})
    data = _zip({"Plan.pdf": b"%PDF", "Los1.x83": b"<GAEB/>", "Los2.zip": nested})

    resp = await client.post(
        "/projects/from-zip",
        files={"file": ("Ausschreibung B247.zip", data, "application/zip")},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project"]["project_name"] == "Ausschreibung B247"
    types = {d["file_name"]: d["document_type"] for d in body["documents"]}
    assert types == {
        "Plan.pdf": DocumentType.PROSE_DOCUMENT,
        "Los1.x83": DocumentType.LV_DOCUMENT,
        "Los2.d83": DocumentType.LV_DOCUMENT,
    }
    assert body["skipped"] == ["Los2.zip/notes.txt"]
    assert len(storage.put) == 3
    jobs = IngestJobRepository(conn)
    for doc in body["documents"]:
        job = await jobs.latest_for_document(UUID(doc["document_uuid"]))
        assert job is not None
        assert job.status == IngestStatus.QUEUED
    info_job = await ProjectInfoJobRepository(conn).latest_for_project(
        UUID(body["project"]["project_uuid"])
    )
    assert info_job is not None
    assert info_job.status == IngestStatus.QUEUED
    assert info_job.language == settings.project_info_language
    assert info_job.overwrite is True


async def test_create_from_zip_rejects_non_zip_name(client: AsyncClient) -> None:
    resp = await client.post(
        "/projects/from-zip",
        files={"file": ("Leistungsbeschreibung.docx", b"x", "application/msword")},
    )
    assert resp.status_code == 422


async def test_create_from_zip_rejects_corrupt_zip(client: AsyncClient) -> None:
    app.dependency_overrides[get_storage] = _RecordingStorage
    resp = await client.post(
        "/projects/from-zip", files={"file": ("tender.zip", b"x", "application/zip")}
    )
    assert resp.status_code == 422


async def test_create_from_zip_over_cap_is_413(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_service, "ZIP_MAX_ENTRIES", 1)
    app.dependency_overrides[get_storage] = _RecordingStorage
    data = _zip({"a.pdf": b"x", "b.pdf": b"y"})
    resp = await client.post(
        "/projects/from-zip", files={"file": ("tender.zip", data, "application/zip")}
    )
    assert resp.status_code == 413
    assert "ZIP_MAX_ENTRIES" in resp.json()["detail"]
