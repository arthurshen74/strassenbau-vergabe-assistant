"""The /ner-flags API with a stubbed LLM (dependency override on get_llm_client):
create-with-analysis roundtrip, retry after failure, summary aggregation, filters.

A ner_fehleranalyse prompt is seeded up front (analyze_flag renders it via get_latest)
and flags are wiped after each test for isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine, get_llm_client
from api.main import app
from shared.clients.llm.client import LLMError
from shared.db.tables.ner_flags import ner_flags
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import NerFailureCategory, PromptType
from shared.models.prompt_version import NewPromptVersion
from shared.services.nlp.error_analysis import NerErrorAnalysis

_TEMPLATE = (
    "FLAG:\n{{flag}}\nTEXT:\n{{text}}\nENTITIES:\n{{entities}}\n"
    "MODEL:\n{{spacy_model}}\nRULES:\n{{entity_rules}}"
)


class _StubLLM:
    def __init__(self) -> None:
        self.result = NerErrorAnalysis(
            category=NerFailureCategory.REGISTER_MISMATCH,
            analysis="Das news-trainierte Modell verkennt das Fachregister.",
        )
        self.error: Exception | None = None

    async def chat_with_reasoning(self, **kwargs: Any) -> tuple[NerErrorAnalysis, None]:
        if self.error is not None:
            raise self.error
        return self.result, None


def _body(**kw: Any) -> dict[str, Any]:
    body = {
        "kind": "wrong_label",
        "span_text": "Asphaltbeton AC",
        "span_start": 0,
        "span_end": 15,
        "sentence_text": "Asphaltbeton AC einbauen.",
        "label": "LOC",
        "expected_label": "BAUSTOFF",
        "user_comment": "LOC ist falsch.",
        "source_text": "Asphaltbeton AC einbauen.",
        "entity_snapshot": [
            {"text": "Asphaltbeton AC", "label": "LOC", "pattern_id": None}
        ],
    }
    body.update(kw)
    return body


@pytest_asyncio.fixture(autouse=True)
async def _seed_and_clean(engine: AsyncEngine) -> AsyncIterator[None]:
    async with unit_of_work(engine) as uow:
        await uow.prompt_versions.add(
            NewPromptVersion(
                prompt_type=PromptType.NER_FEHLERANALYSE,
                model_name="openai/gpt-5.4",
                system_prompt=_TEMPLATE,
                temperature=None,
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(delete(ner_flags))


@pytest_asyncio.fixture
async def client_stub(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncClient, _StubLLM]]:
    stub = _StubLLM()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_llm_client] = lambda: stub
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, stub
    finally:
        app.dependency_overrides.clear()


async def test_create_with_analysis_roundtrip(
    client_stub: tuple[AsyncClient, _StubLLM],
) -> None:
    client, _ = client_stub
    response = await client.post("/ner-flags", json=_body())

    assert response.status_code == 201
    flag = response.json()
    assert flag["category"] == NerFailureCategory.REGISTER_MISMATCH.value
    assert flag["effective_category"] == NerFailureCategory.REGISTER_MISMATCH.value
    assert flag["llm_analysis"]
    assert flag["llm_model"] == "openai/gpt-5.4"
    assert flag["analyzed_at"] is not None
    assert flag["status"] == "open"


async def test_retry_after_failure(client_stub: tuple[AsyncClient, _StubLLM]) -> None:
    client, stub = client_stub
    stub.error = LLMError("boom")

    created = await client.post("/ner-flags", json=_body())
    assert created.status_code == 201
    flag = created.json()
    assert flag["category"] is None
    assert flag["analyzed_at"] is None

    stub.error = None
    retried = await client.post(f"/ner-flags/{flag['ner_flag_uuid']}/analyze")
    assert retried.status_code == 200
    assert retried.json()["category"] == NerFailureCategory.REGISTER_MISMATCH.value


async def test_summary_aggregation(client_stub: tuple[AsyncClient, _StubLLM]) -> None:
    client, stub = client_stub

    stub.result = NerErrorAnalysis(
        category=NerFailureCategory.REGISTER_MISMATCH, analysis="a"
    )
    await client.post("/ner-flags", json=_body())
    await client.post("/ner-flags", json=_body())
    stub.result = NerErrorAnalysis(category=NerFailureCategory.MISSING_RULE, analysis="b")
    await client.post("/ner-flags", json=_body())

    summary = (await client.get("/ner-flags/summary")).json()
    by_cat = {c["category"]: c for c in summary["by_category"]}
    assert summary["total"] == 3
    assert by_cat["register_mismatch"]["total"] == 2
    assert by_cat["missing_rule"]["total"] == 1


async def test_filters(client_stub: tuple[AsyncClient, _StubLLM]) -> None:
    client, stub = client_stub

    stub.result = NerErrorAnalysis(
        category=NerFailureCategory.REGISTER_MISMATCH, analysis="a"
    )
    await client.post("/ner-flags", json=_body())
    stub.result = NerErrorAnalysis(category=NerFailureCategory.TOKENIZATION, analysis="b")
    missed = (await client.post("/ner-flags", json=_body(kind="missed_entity"))).json()

    by_kind = (await client.get("/ner-flags", params={"kind": "missed_entity"})).json()
    assert {f["ner_flag_uuid"] for f in by_kind} == {missed["ner_flag_uuid"]}

    by_category = (
        await client.get("/ner-flags", params={"category": "tokenization"})
    ).json()
    assert {f["ner_flag_uuid"] for f in by_category} == {missed["ner_flag_uuid"]}

    # Resolve it and filter by status.
    await client.patch(
        f"/ner-flags/{missed['ner_flag_uuid']}",
        json={"status": "resolved", "resolved_note": "added rule"},
    )
    resolved = (await client.get("/ner-flags", params={"status": "resolved"})).json()
    assert {f["ner_flag_uuid"] for f in resolved} == {missed["ner_flag_uuid"]}
