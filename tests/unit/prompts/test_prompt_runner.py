from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from shared.models.chat_message import ChatMessage
from shared.models.enums import PromptType
from shared.models.llm_output_schemas import LVExtraction, MultiQueryRewrite
from shared.models.prompt_version import PromptVersion
from shared.services.prompt_runner import (
    PromptRenderError,
    PromptRunner,
    PromptVersionNotFoundError,
    render_template,
)


def _pv(
    prompt_type: PromptType,
    *,
    system_prompt: str = "sys",
    version: int = 1,
    model_name: str = "anthropic/claude-sonnet-4.6",
    temperature: float = 0.3,
    top_p: float | None = 0.9,
) -> PromptVersion:
    return PromptVersion(
        prompt_version_uuid=uuid4(),
        prompt_type=prompt_type,
        version=version,
        model_name=model_name,
        system_prompt=system_prompt,
        temperature=temperature,
        top_p=top_p,
        created_at=datetime.now(UTC),
    )


class _StubRepo:
    def __init__(self, pv: PromptVersion | None) -> None:
        self._pv = pv
        self.latest_calls: list[PromptType] = []
        self.pinned_calls: list[tuple[PromptType, int]] = []

    async def get_latest(self, prompt_type: PromptType) -> PromptVersion | None:
        self.latest_calls.append(prompt_type)
        return self._pv

    async def get_by_type_and_version(
        self, prompt_type: PromptType, version: int
    ) -> PromptVersion | None:
        self.pinned_calls.append((prompt_type, version))
        return self._pv


class _StubLLM:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._result


def _runner(pv: PromptVersion | None, result: Any) -> tuple[PromptRunner, _StubRepo, _StubLLM]:
    repo = _StubRepo(pv)
    llm = _StubLLM(result)
    return PromptRunner(repo, llm), repo, llm  # type: ignore[arg-type]


# --- _render -------------------------------------------------------------


def test_render_substitutes_double_braces() -> None:
    assert render_template("Give {{n}} variants", {"n": "3"}) == "Give 3 variants"
    assert render_template("Give {{ n }} variants", {"n": "3"}) == "Give 3 variants"


def test_render_without_placeholders_is_unchanged() -> None:
    assert render_template("plain text", None) == "plain text"


def test_render_raises_on_missing_variable() -> None:
    with pytest.raises(PromptRenderError):
        render_template("Hello {{name}}", {})
    with pytest.raises(PromptRenderError):
        render_template("Hello {{name}}", None)


# --- generate_query_variants --------------------------------------------


async def test_generate_query_variants_renders_and_passes_attribution() -> None:
    pv = _pv(PromptType.MULTI_QUESTION_GENERATOR, system_prompt="Return {{n}} variants.")
    runner, repo, llm = _runner(pv, MultiQueryRewrite(queries=["a", "b", "c", "d", "e"]))

    out = await runner.generate_query_variants("how to pour concrete", n=3, project_uuid=None)

    assert out == ["a", "b", "c"]
    assert repo.latest_calls == [PromptType.MULTI_QUESTION_GENERATOR]

    call = llm.calls[0]
    assert call["model"] == pv.model_name
    assert call["output_model"] is MultiQueryRewrite
    assert call["temperature"] == pv.temperature
    assert call["top_p"] == pv.top_p
    assert call["chat_prompt_type"] == PromptType.MULTI_QUESTION_GENERATOR.value
    assert call["chat_prompt_version"] == pv.version

    messages = call["messages"]
    assert messages[0] == {"role": "system", "content": "Return 3 variants."}
    assert isinstance(messages[1], ChatMessage)
    assert messages[1].role == "user"
    assert messages[1].content == "how to pour concrete"


async def test_generate_query_variants_pins_version() -> None:
    pv = _pv(PromptType.MULTI_QUESTION_GENERATOR, system_prompt="Return {{n}} variants.", version=4)
    runner, repo, _ = _runner(pv, MultiQueryRewrite(queries=["a", "b"]))

    await runner.generate_query_variants("q", n=2, version=4)

    assert repo.latest_calls == []
    assert repo.pinned_calls == [(PromptType.MULTI_QUESTION_GENERATOR, 4)]


# --- run_lv_extraction ---------------------------------------------------


async def test_run_lv_extraction_renders_document_and_requests_schema() -> None:
    pv = _pv(PromptType.LV_EXTRACTION, system_prompt="Segment:\n{{numbered_document}}")
    runner, repo, llm = _runner(pv, LVExtraction(positions=[]))
    project_uuid, job_uuid, document_uuid = uuid4(), uuid4(), uuid4()

    out = await runner.run_lv_extraction(
        "0\tfirst line",
        project_uuid=project_uuid,
        ingest_job_uuid=job_uuid,
        document_uuid=document_uuid,
    )

    assert isinstance(out, LVExtraction)
    assert repo.latest_calls == [PromptType.LV_EXTRACTION]
    call = llm.calls[0]
    assert call["output_model"] is LVExtraction
    assert call["chat_prompt_type"] == PromptType.LV_EXTRACTION.value
    assert call["messages"][0] == {"role": "system", "content": "Segment:\n0\tfirst line"}
    # The owning document must reach chat() so the LV_PARSE usage row is attributed to it.
    assert call["project_uuid"] == project_uuid
    assert call["ingest_job_uuid"] == job_uuid
    assert call["document_uuid"] == document_uuid


# --- run_text ------------------------------------------------------------


async def test_run_text_returns_text_without_output_model() -> None:
    pv = _pv(PromptType.DISPATCHER, system_prompt="route requests")
    runner, _, llm = _runner(pv, "hello")

    out = await runner.run_text(
        PromptType.DISPATCHER, messages=[ChatMessage(role="user", content="hi")]
    )

    assert out == "hello"
    # A free-form prompt type must not request structured output.
    assert "output_model" not in llm.calls[0]


# --- missing prompt ------------------------------------------------------


async def test_missing_prompt_raises() -> None:
    runner, _, _ = _runner(None, "x")
    with pytest.raises(PromptVersionNotFoundError):
        await runner.run_text(PromptType.DISPATCHER, messages=[])
