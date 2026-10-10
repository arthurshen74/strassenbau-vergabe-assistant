"""The /ingest-jobs console API: the merged list, the diffed list stream, and the
Projektinfo requeue + activity stream.

The routes read through the engine (their own connections), so data is committed via
the engine and each test deletes its project afterwards (everything cascades from it).
The SSE endpoints never end on their own, so they are driven with a raw ASGI call that
collects body chunks and disconnects once enough events arrived.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine
from api.main import app
from shared.config import settings
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.project_info_jobs import project_info_jobs
from shared.db.tables.projects import projects
from shared.db.unit_of_work import unit_of_work
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.models.project_info_activity import NewProjectInfoActivity
from shared.models.project_info_job import NewProjectInfoJob

_STREAM_TIMEOUT = 10.0


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ingest_status_poll_interval_seconds", 0.05)


@pytest_asyncio.fixture
async def seeded(engine: AsyncEngine) -> AsyncIterator[dict[str, UUID]]:
    """A project with one queued ingest job and one queued Projektinfo job."""
    async with unit_of_work(engine) as uow:
        project = await uow.projects.add(NewProject(project_name="Console API"))
        doc = await uow.documents.add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.PROSE_DOCUMENT,
                file_name="console.pdf",
                number_of_pages=1,
            )
        )
        ingest = await uow.ingest_jobs.add(NewIngestJob(document_uuid=doc.document_uuid))
        info = await uow.project_info_jobs.add(
            NewProjectInfoJob(project_uuid=project.project_uuid, language="de")
        )
    yield {
        "project": project.project_uuid,
        "ingest_job": ingest.job_uuid,
        "info_job": info.job_uuid,
    }
    async with engine.begin() as conn:
        await conn.execute(delete(projects).where(projects.c.project_uuid == project.project_uuid))


async def _sse(path: str, query: str, want: int) -> list[tuple[str, Any]]:
    """GET an SSE endpoint, return the first `want` events (or every event if the
    stream ends first), then disconnect."""
    sent: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    disconnect = asyncio.Event()

    async def receive() -> dict[str, Any]:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        await sent.put(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query.encode(),
        "headers": [(b"host", b"test"), (b"accept", b"text/event-stream")],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    task = asyncio.create_task(app(scope, receive, send))
    events: list[tuple[str, Any]] = []
    buffer = ""
    try:
        async with asyncio.timeout(_STREAM_TIMEOUT):
            while len(events) < want:
                message = await sent.get()
                if message["type"] == "http.response.start":
                    assert message["status"] == 200
                    continue
                buffer += message.get("body", b"").decode()
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    lines = dict(line.split(": ", 1) for line in raw.split("\n") if ": " in line)
                    if "event" in lines:
                        events.append((lines["event"], json.loads(lines["data"])))
                if not message.get("more_body", False):
                    break
    finally:
        disconnect.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return events


async def test_active_list_returns_both_kinds(client: AsyncClient, seeded: dict[str, UUID]) -> None:
    resp = await client.get(
        "/ingest-jobs", params={"active": "true", "project_uuid": str(seeded["project"])}
    )
    assert resp.status_code == 200, resp.text
    rows = {r["kind"]: r for r in resp.json()}
    assert set(rows) == {"ingest", "project_info"}
    assert rows["ingest"]["job_uuid"] == str(seeded["ingest_job"])
    assert rows["ingest"]["file_name"] == "console.pdf"
    assert rows["project_info"]["job_uuid"] == str(seeded["info_job"])
    assert rows["project_info"]["file_name"] is None
    assert rows["project_info"]["document_uuid"] is None
    assert rows["project_info"]["project_name"] == "Console API"


async def test_list_stream_emits_snapshot_then_change(
    client: AsyncClient, engine: AsyncEngine, seeded: dict[str, UUID]
) -> None:
    query = f"active=true&project_uuid={seeded['project']}"

    async def change_status_after_first_snapshot() -> None:
        await asyncio.sleep(0.3)
        async with engine.begin() as conn:
            await conn.execute(
                update(ingest_jobs)
                .where(ingest_jobs.c.job_uuid == seeded["ingest_job"])
                .values(status=IngestStatus.RUNNING, locked_by="w-test")
            )

    changer = asyncio.create_task(change_status_after_first_snapshot())
    events = await _sse("/ingest-jobs/stream", query, want=2)
    await changer

    assert [name for name, _ in events] == ["console_jobs", "console_jobs"]
    first = {j["kind"]: j for j in events[0][1]["jobs"]}
    second = {j["kind"]: j for j in events[1][1]["jobs"]}
    assert first["ingest"]["status"] == "queued"
    assert second["ingest"]["status"] == "running"
    assert second["ingest"]["locked_by"] == "w-test"
    assert second["project_info"]["status"] == "queued"


async def test_project_info_requeue(client: AsyncClient, engine: AsyncEngine, seeded: dict[str, UUID]) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(project_info_jobs)
            .where(project_info_jobs.c.job_uuid == seeded["info_job"])
            .values(status=IngestStatus.FAILED, attempts=3, error="boom", locked_by="w")
        )

    resp = await client.post(f"/ingest-jobs/project-info/{seeded['info_job']}/requeue")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["status"], body["attempts"], body["error"]) == ("queued", 0, None)
    missing = await client.post(f"/ingest-jobs/project-info/{seeded['ingest_job']}/requeue")
    assert missing.status_code == 404


async def test_ingest_requeue(client: AsyncClient, seeded: dict[str, UUID]) -> None:
    resp = await client.post(f"/ingest-jobs/{seeded['ingest_job']}/requeue")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"


async def test_project_info_activity_stream_ends_when_done_and_drained(
    engine: AsyncEngine, seeded: dict[str, UUID]
) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        async with unit_of_work(engine) as uow:
            await uow.project_info_activity.add_many(
                [
                    NewProjectInfoActivity(
                        job_uuid=seeded["info_job"],
                        project_uuid=seeded["project"],
                        worker_id="w",
                        phase=phase,
                        message=message,
                    )
                    for phase, message in [("claim", "claimed"), ("write", "done in 0.1 s")]
                ]
            )
            await uow.conn.execute(
                update(project_info_jobs)
                .where(project_info_jobs.c.job_uuid == seeded["info_job"])
                .values(status=IngestStatus.DONE)
            )

        events = await _sse(
            f"/ingest-jobs/project-info/{seeded['info_job']}/activity/stream", "", want=99
        )
    finally:
        app.dependency_overrides.clear()

    assert [name for name, _ in events] == ["project_info_activity"] * 2
    assert [data["message"] for _, data in events] == ["claimed", "done in 0.1 s"]
    assert events[0][1]["project_uuid"] == str(seeded["project"])
