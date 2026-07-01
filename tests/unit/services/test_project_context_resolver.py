from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from shared.models.enums import PromptType
from shared.models.prompt_version import PromptVersion
from shared.services.kalkulation_v2.globale_variablen import GLOBALE_VARIABLEN, VAR_DEPONIE_LOCATION
from shared.services.project_context.llm import GlobaleAufloesung, resolve_globale
from shared.services.project_context.service import _quelle_referenz


def test_quelle_referenz_captures_policy_and_treffer() -> None:
    chunk_uuid = uuid4()
    doc_uuid = uuid4()
    ctx = SimpleNamespace(
        reranked=[SimpleNamespace(chunk_uuid=chunk_uuid, relevance_score=0.81)],
        context=[
            SimpleNamespace(
                chunk_uuid=chunk_uuid,
                source_doc_uuid=doc_uuid,
                source_doc_pages=[12, 13],
            )
        ],
        config=SimpleNamespace(
            modality=SimpleNamespace(value="PLUS"),
            multi_query=True,
            use_bm25=True,
            use_cross_encoder=True,
            top_k=8,
        ),
    )

    referenz = _quelle_referenz(ctx)  # type: ignore[arg-type]

    assert referenz["retrieval"] == {
        "modality": "PLUS",
        "multi_query": True,
        "use_bm25": True,
        "use_cross_encoder": True,
        "top_k": 8,
    }
    assert referenz["treffer"] == [
        {
            "document_uuid": str(doc_uuid),
            "seite": 12,
            "chunk_uuid": str(chunk_uuid),
            "score": 0.81,
        }
    ]


class _StubLLM:
    def __init__(self, result: GlobaleAufloesung) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def chat_with_reasoning(self, **kwargs: Any) -> tuple[GlobaleAufloesung, str | None]:
        self.calls.append(kwargs)
        return self._result, "weil im Text genannt"


def _prompt() -> PromptVersion:
    return PromptVersion(
        prompt_version_uuid=uuid4(),
        prompt_type=PromptType.PROJECT_CONTEXT_RESOLVE,
        version=1,
        model_name="openai/gpt-5.4",
        system_prompt="Du löst eine globale Variable auf.",
        created_at=datetime.now(timezone.utc),
    )


async def test_resolve_globale_forwards_prompt_and_snippets() -> None:
    result = GlobaleAufloesung(gefunden=True, wert="Deponie Sangerhausen", konfidenz=0.9, beleg="…")
    llm = _StubLLM(result)

    ext, summary = await resolve_globale(
        llm,  # type: ignore[arg-type]
        GLOBALE_VARIABLEN[VAR_DEPONIE_LOCATION],
        ["Der Abtrag wird zur Deponie Sangerhausen verbracht."],
        prompt=_prompt(),
    )

    assert ext.wert == "Deponie Sangerhausen"
    assert summary == "weil im Text genannt"
    call = llm.calls[0]
    assert call["model"] == "openai/gpt-5.4"
    assert call["output_model"] is GlobaleAufloesung
    assert call["chat_prompt_type"] == PromptType.PROJECT_CONTEXT_RESOLVE.value
    # The snippet text reaches the user message.
    assert "Sangerhausen" in call["messages"][1]["content"]
