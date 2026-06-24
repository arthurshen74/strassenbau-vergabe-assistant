"""The LLM call sites of the kalkulation_v2 position-calculation graph.

Four prompts, each on a DB-backed, versioned PromptVersion (the caller resolves it
via shared.services.calculator.prompts and passes it in; model, system text,
temperature and reasoning effort all come from it):

  1. classify_leistung    -> LeistungKlassifikation  (which Leistung is this position?)
  2. extract_chat_values   -> ChatWerte               (values the Kalkulator stated pre-launch)
  3. extract_value         -> WertExtraktion          (one generic extractor: Langtext OR RAG)
  4. narrate_output        -> str                      (the long-form result narration)

The structured sites go through `chat_with_reasoning` (validated output + the
provider's reasoning summary, best-effort). Numbers are read VERBATIM from text;
coercion to Decimal happens deterministically in the graph, never here. Mock mode is
handled by the graph nodes (which skip these calls entirely), so these are pure
live-LLM sites.
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

_REASONING = ("2-5 kurze Denkschritte, ZUERST: was der Text sagt -> welche Regel greift "
              "-> Schluss. Belege mit wörtlichem Zitat.")

# Sentinel the classifier returns when no offered Leistung fits.
LEISTUNG_UNBEKANNT = "unbekannt"


class LeistungKlassifikation(BaseModel):
    reasoning: list[str] = Field(default=[], description=_REASONING)
    leistung_key: str = Field(description="Genau einer der angebotenen Leistung-Keys, oder 'unbekannt'")
    konfidenz: float = Field(ge=0, le=1)
    notizen: str = Field(description="1-2 Sätze, mit dem entscheidenden Wortlaut")


class ChatWertZuweisung(BaseModel):
    name: str = Field(description="Exakter Variablenname aus dem angebotenen Katalog")
    wert: str = Field(description="Der genannte Wert, wörtlich übernommen (keine Umrechnung)")
    beleg: str = Field(description="Die Chat-Stelle, die ihn gesetzt hat")


class ChatWerte(BaseModel):
    zuweisungen: list[ChatWertZuweisung] = Field(
        default=[], description="Jede explizite Zuweisung; [] wenn keine")


class WertExtraktion(BaseModel):
    reasoning: list[str] = Field(default=[], description=_REASONING)
    gefunden: bool = Field(description="True nur, wenn der Beleg den Wert eindeutig hergibt")
    wert: str | None = Field(default=None, description="Der gelesene Wert, wörtlich; None wenn nicht gefunden")
    konfidenz: float = Field(ge=0, le=1)
    beleg: str | None = Field(default=None, description="Wörtliches Belegzitat")


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [
        {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
        {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: user},
    ]


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


async def classify_leistung(
    llm: LLMClient,
    position: dict,
    leistung_index: list[dict],
    snippets: list[str],
    *,
    prompt: PromptVersion,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[LeistungKlassifikation, str | None]:
    user = (f"LV-Position:\n{_dump(position)}\n\n"
            f"Angebotene Leistungen (wähle GENAU einen leistung_key):\n{_dump(leistung_index)}\n\n"
            f"Projektkontext (Auszüge):\n{_dump(snippets)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=LeistungKlassifikation,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


async def extract_chat_values(
    llm: LLMClient,
    transcript: list[dict],
    variablen_katalog: list[dict],
    *,
    prompt: PromptVersion,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[ChatWerte, str | None]:
    user = (f"Chatverlauf:\n{_dump(transcript)}\n\n"
            f"Variablen-Katalog (wähle names NUR hieraus):\n{_dump(variablen_katalog)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=ChatWerte,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


async def extract_value(
    llm: LLMClient,
    variable: dict,
    evidence: dict,
    *,
    prompt: PromptVersion,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[WertExtraktion, str | None]:
    """One generic extractor, reused for the Langtext step (evidence = position
    Langtext/Hinweise) and the RAG step (evidence = retrieved snippets)."""
    user = (f"Gesuchte Variable:\n{_dump(variable)}\n\n"
            f"Beleg (verwende NUR dies):\n{_dump(evidence)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=WertExtraktion,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


async def narrate_output(
    llm: LLMClient,
    ekt_zeile: dict,
    nachweis_tabelle: list[dict],
    *,
    prompt: PromptVersion,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> str:
    user = (f"EKT-Ergebnis:\n{_dump(ekt_zeile)}\n\n"
            f"Nachweistabelle (Herleitung):\n{_dump(nachweis_tabelle)}")
    text = await llm.chat(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        temperature=prompt.temperature,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )
    assert isinstance(text, str)
    return text
