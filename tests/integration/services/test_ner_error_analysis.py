"""analyze_flag with a stubbed LLM: prompt assembly, provenance, and failure handling.

Uses the committed `engine` (analyze_flag opens its own connections), so a NER
error-analysis prompt and an entity rule are seeded up front and flags are wiped
after each test for isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import LLMError
from shared.db.tables.ner_flags import ner_flags
from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import NewEntityRule
from shared.models.enums import NerFailureCategory, NerFlagKind, PromptType
from shared.models.ner_flag import NerFlag, NewNerFlag, SnapshotEntity
from shared.models.prompt_version import NewPromptVersion
from shared.services.nlp.error_analysis import (
    NerErrorAnalysis,
    SuggestedRuleOut,
    analyze_flag,
)

_TEMPLATE = (
    "FLAG:\n{{flag}}\n\nTEXT:\n{{text}}\n\nENTITIES:\n{{entities}}\n\n"
    "MODEL:\n{{spacy_model}}\n\nRULES:\n{{entity_rules}}"
)

_RULE_ID = "baustoff_bordstein"


class _StubLLM:
    def __init__(self, result: NerErrorAnalysis | None = None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def chat_with_reasoning(self, **kwargs: Any) -> tuple[NerErrorAnalysis, None]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result, None


@pytest_asyncio.fixture(autouse=True)
async def _seed_and_clean(engine: AsyncEngine) -> AsyncIterator[None]:
    async with unit_of_work(engine) as uow:
        await uow.prompt_versions.add(
            NewPromptVersion(
                prompt_type=PromptType.NER_FEHLERANALYSE,
                model_name="openai/gpt-5.4",
                system_prompt=_TEMPLATE,
                temperature=None,
                reasoning_effort="medium",
            )
        )
        existing = await uow.entity_rules.list_enabled()
        if not any(r.pattern_id == _RULE_ID for r in existing):
            await uow.entity_rules.add(
                NewEntityRule(
                    label="BAUSTOFF",
                    pattern=[{"LOWER": "bordstein"}],
                    pattern_id=_RULE_ID,
                )
            )
    yield
    async with engine.begin() as conn:
        await conn.execute(delete(ner_flags))


def _new_flag(**kw: Any) -> NewNerFlag:
    return NewNerFlag(
        kind=NerFlagKind.WRONG_LABEL,
        span_text="Asphaltbeton AC",
        span_start=0,
        span_end=15,
        sentence_text="Asphaltbeton AC einbauen.",
        label="LOC",
        expected_label="BAUSTOFF",
        user_comment="LOC ist falsch, das ist ein Baustoff.",
        source_text="Asphaltbeton AC einbauen. Bordstein versetzen.",
        entity_snapshot=[
            SnapshotEntity(text="Asphaltbeton AC", label="LOC", pattern_id=None)
        ],
        **kw,
    )


async def _add_flag(engine: AsyncEngine) -> NerFlag:
    async with unit_of_work(engine) as uow:
        return await uow.ner_flags.add(_new_flag())


async def test_prompt_has_all_sections_and_records_provenance(engine: AsyncEngine) -> None:
    flag = await _add_flag(engine)
    stub = _StubLLM(
        result=NerErrorAnalysis(
            reasoning=["news-trained model", "technical register"],
            category=NerFailureCategory.REGISTER_MISMATCH,
            analysis="Das news-trainierte Modell verkennt das Fachvokabular.",
        )
    )

    updated = await analyze_flag(flag, engine=engine, llm=stub)  # type: ignore[arg-type]

    system = stub.calls[0]["messages"][0]["content"]
    # All five context sections present.
    assert "Asphaltbeton AC" in system  # flagged span (flag section)
    assert "Bordstein versetzen." in system  # analyzed source text
    assert "[LOC]" in system and "statistisches Modell" in system  # entities + provenance
    assert "de_core_news_lg" in system  # spaCy model version
    assert _RULE_ID in system  # entity rules JSON

    assert updated.category == NerFailureCategory.REGISTER_MISMATCH
    assert updated.effective_category == NerFailureCategory.REGISTER_MISMATCH
    assert updated.llm_analysis is not None
    assert updated.llm_model == "openai/gpt-5.4"
    assert updated.prompt_version is not None
    assert updated.spacy_model_version is not None
    assert updated.analyzed_at is not None


async def test_suggested_rule_persisted(engine: AsyncEngine) -> None:
    flag = await _add_flag(engine)
    stub = _StubLLM(
        result=NerErrorAnalysis(
            category=NerFailureCategory.MISSING_RULE,
            analysis="Keine Regel deckt das Vokabular ab.",
            suggested_rule=SuggestedRuleOut(
                label="BAUSTOFF",
                pattern=[{"LOWER": "asphaltbeton"}],
                pattern_id="baustoff_asphaltbeton",
            ),
        )
    )

    updated = await analyze_flag(flag, engine=engine, llm=stub)  # type: ignore[arg-type]

    assert updated.suggested_rule is not None
    assert updated.suggested_rule.pattern_id == "baustoff_asphaltbeton"


async def test_llm_failure_keeps_flag_with_null_analysis(engine: AsyncEngine) -> None:
    flag = await _add_flag(engine)
    stub = _StubLLM(error=LLMError("boom"))

    updated = await analyze_flag(flag, engine=engine, llm=stub)  # type: ignore[arg-type]

    assert updated.category is None
    assert updated.llm_analysis is None
    # The flag still exists in the DB, retriable.
    async with unit_of_work(engine) as uow:
        fetched = await uow.ner_flags.get(flag.ner_flag_uuid)
    assert fetched is not None
    assert fetched.analyzed_at is None
