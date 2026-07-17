"""The /nlp/* API: document listing, reflowed text with line classification,
analysis with include-list validation, and dep-render caching.

Layout regions are pre-seeded for the current docling version, so no Docling
inference (and no storage access — the stub trips on any call) happens in tests.
Data is committed via the engine because the services open their own connections.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine, get_storage
from api.main import app
from shared.db.tables.nlp_render_cache import nlp_render_cache
from shared.db.unit_of_work import unit_of_work
from shared.models.document import NewDocument
from shared.models.enums import BlockType, DocumentType
from shared.models.nlp import DocumentLayout, LayoutRegion
from shared.models.project import NewProject
from shared.models.source_line import NewSourceLine
from shared.services.nlp.layout import (
    LABEL_PAGE_FOOTER,
    LABEL_SECTION_HEADER,
    layout_model_version,
)


class _TripwireStorage:
    """Any storage access in these tests means the layout cache was bypassed."""

    def get_object(self, key: str) -> bytes:
        raise AssertionError(f"storage must not be touched (key={key})")


_PITCH = 12.7


def _lines(document_uuid: UUID) -> list[NewSourceLine]:
    lines: list[NewSourceLine] = []
    line_id = 0
    texts = {
        1: ["2.1 Allgemeines", "Der Auftragnehmer erbringt die Leistung fristgerecht."],
        2: ["Die Baustelle ist gegen unbefugtes Betreten zu sichern."],
        3: ["Alle Nachweise sind dem Auftraggeber vorzulegen."],
    }
    for page in (1, 2, 3):
        for i, text in enumerate(texts[page]):
            y = 100.0 + i * _PITCH
            lines.append(
                NewSourceLine(
                    document_uuid=document_uuid,
                    line_id=line_id,
                    page=page,
                    bbox=(70.0, y, 470.0, y + 10.0),
                    line_text=text,
                )
            )
            line_id += 1
        lines.append(
            NewSourceLine(
                document_uuid=document_uuid,
                line_id=line_id,
                page=page,
                bbox=(400.0, 800.0, 470.0, 810.0),
                line_text=f"Seite {page}/3",
            )
        )
        line_id += 1
    return lines


def _regions() -> list[LayoutRegion]:
    regions = [
        LayoutRegion(page=1, label=LABEL_SECTION_HEADER, bbox=(60.0, 95.0, 480.0, 112.0)),
    ]
    for page in (1, 2, 3):
        regions.append(
            LayoutRegion(page=page, label=LABEL_PAGE_FOOTER, bbox=(390.0, 795.0, 480.0, 815.0))
        )
    return regions


@pytest_asyncio.fixture
async def seeded_document(engine: AsyncEngine) -> AsyncIterator[UUID]:
    async with unit_of_work(engine) as uow:
        project = await uow.projects.add(
            NewProject(
                vergabe_id=f"VG-NLP-{uuid4().hex[:8]}",
                project_name="NLP Testprojekt",
                project_description="d",
                vergabestelle="V",
            )
        )
        document = await uow.documents.add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.PROSE_DOCUMENT,
                file_name="bb_nlp_test.pdf",
                number_of_pages=3,
            )
        )
        await uow.source_lines.add_many(_lines(document.document_uuid))
        await uow.document_layout_regions.put(
            DocumentLayout(
                document_uuid=document.document_uuid,
                model_version=layout_model_version(),
                regions=_regions(),
            )
        )
    yield document.document_uuid
    async with unit_of_work(engine) as uow:
        await uow.projects.delete(project.project_uuid)


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_storage] = lambda: _TripwireStorage()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def test_list_documents(client: AsyncClient, seeded_document: UUID) -> None:
    response = await client.get("/nlp/documents")

    assert response.status_code == 200
    entries = [d for d in response.json() if d["document_uuid"] == str(seeded_document)]
    assert len(entries) == 1
    assert entries[0]["project_name"] == "NLP Testprojekt"
    assert entries[0]["file_name"] == "bb_nlp_test.pdf"


async def test_document_text_classifies_lines(
    client: AsyncClient, seeded_document: UUID
) -> None:
    response = await client.get(f"/nlp/documents/{seeded_document}/text")

    assert response.status_code == 200
    body = response.json()
    by_text = {line["text"]: line["block_type"] for line in body["lines"]}
    assert by_text["Seite 1/3"] == BlockType.FURNITURE.value
    assert by_text["2.1 Allgemeines"] == BlockType.HEADING.value
    assert by_text["Die Baustelle ist gegen unbefugtes Betreten zu sichern."] == (
        BlockType.PROSE.value
    )
    assert all(b["block_type"] != BlockType.FURNITURE.value for b in body["blocks"])


async def test_analyze_default_include_blocks(
    client: AsyncClient, seeded_document: UUID
) -> None:
    response = await client.post(
        "/nlp/analyze", json={"document_uuid": str(seeded_document)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["include_blocks"] == [
        BlockType.PROSE.value,
        BlockType.HEADING.value,
        BlockType.LIST_ITEM.value,
    ]
    sentence_texts = [s["text"] for s in body["sentences"]]
    assert "Der Auftragnehmer erbringt die Leistung fristgerecht." in sentence_texts
    assert not any("Seite" in t for t in sentence_texts)
    assert body["pos"]["token_count"] > 0
    assert sum(t["count"] for t in body["pos"]["ud"]) == body["pos"]["token_count"]


async def test_analyze_rejects_furniture(client: AsyncClient, seeded_document: UUID) -> None:
    response = await client.post(
        "/nlp/analyze",
        json={
            "document_uuid": str(seeded_document),
            "include_blocks": [BlockType.FURNITURE.value],
        },
    )

    assert response.status_code == 422


async def test_dep_render_cached(client: AsyncClient, engine: AsyncEngine) -> None:
    sentence = "Der Bieter kalkuliert seine Einheitspreise sorgfältig."

    first = await client.post("/nlp/render", json={"style": "dep", "text": sentence})
    assert first.status_code == 200
    assert first.json()["markup"].lstrip().startswith("<svg")

    async with engine.connect() as conn:
        count = len(
            (await conn.execute(select(nlp_render_cache.c.cache_key))).all()
        )
    assert count >= 1

    second = await client.post("/nlp/render", json={"style": "dep", "text": sentence})
    assert second.json()["markup"] == first.json()["markup"]


async def test_ent_render_not_cached(client: AsyncClient, engine: AsyncEngine) -> None:
    response = await client.post(
        "/nlp/render",
        json={"style": "ent", "text": "Die LSBB prüft die Baumaßnahme in Magdeburg."},
    )

    assert response.status_code == 200
    markup = response.json()["markup"]
    assert "<svg" not in markup
    async with engine.connect() as conn:
        rows = (await conn.execute(select(nlp_render_cache.c.style))).scalars().all()
    assert all(style == "dep" for style in rows)
