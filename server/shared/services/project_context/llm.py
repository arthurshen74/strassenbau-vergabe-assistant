"""The dedicated synthesis LLM site for project context globals
(PROJECT_CONTEXT_RESOLVE).

`resolve_globale` distills the hybrid-RAG chunks for ONE global into a structured
`{wert, konfidenz, beleg}` (reasoning-augmented). One variable per call: the retrieval
is already focused on that variable's `rag_prompt`, so there is no multi-variable pass
(which would mix unrelated chunks and invite cross-variable hallucination). Mirrors the
structured sites in `shared.services.calculator.llm_calls`; numbers are read verbatim,
never coerced here.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, Field

from shared.clients.llm.client import (
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
    ROLE_SYSTEM,
    ROLE_USER,
    LLMClient,
)
from shared.models.prompt_version import PromptVersion
from shared.services.kalkulation_v2.globale_variablen import GlobaleVariable

_REASONING = (
    "2-5 kurze Denkschritte, ZUERST: was die Auszüge sagen -> welche Stelle den Wert "
    "hergibt -> Schluss. Belege mit wörtlichem Zitat."
)


class GlobaleAufloesung(BaseModel):
    reasoning: list[str] = Field(default=[], description=_REASONING)
    gefunden: bool = Field(
        description="True nur, wenn die Auszüge den Wert eindeutig hergeben"
    )
    wert: str | None = Field(
        default=None,
        description="Der gelesene Wert, wörtlich (Adresse oder Zahl); None wenn nicht "
        "gefunden",
    )
    konfidenz: float = Field(ge=0, le=1)
    beleg: str | None = Field(
        default=None, description="Wörtliches Belegzitat aus den Auszügen"
    )


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [
        {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
        {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: user},
    ]


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


async def resolve_globale(
    llm: LLMClient,
    variable: GlobaleVariable,
    snippets: list[str],
    *,
    prompt: PromptVersion,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[GlobaleAufloesung, str | None]:
    """Synthesize one global's value from its retrieved snippets."""
    gesucht = {
        "name": variable.name,
        "bezeichnung": variable.bezeichnung,
        "einheit": variable.einheit,
        "ist_standort": variable.ist_standort,
    }
    user = (
        f"Gesuchte globale Variable:\n{_dump(gesucht)}\n\n"
        f"Auszüge (verwende NUR diese):\n{_dump(snippets)}"
    )
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=GlobaleAufloesung,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )
