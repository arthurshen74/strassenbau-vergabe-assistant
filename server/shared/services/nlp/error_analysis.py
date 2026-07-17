"""One-shot LLM error analysis for a flagged NER misprediction.

Assembles the flagged span, the analyzed text, the flag-time entities with their
provenance (pattern id or a statistical-model marker), the spaCy model identity, and
the full enabled entity-rule set into the seeded `ner_fehleranalyse` prompt, calls the
LLM for a structured categorization, and writes the result (category, prose analysis,
optional rule suggestion) plus provenance back onto the flag. An LLM failure leaves the
flag with a null analysis; the same function is the retry path.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.client import (
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
    ROLE_SYSTEM,
    ROLE_USER,
    LLMClient,
    LLMError,
)
from shared.db.unit_of_work import unit_of_work
from shared.models.entity_rule import EntityPattern, EntityRule
from shared.models.enums import NerFailureCategory, NerFlagKind, PromptType
from shared.models.ner_flag import NerFlag, SnapshotEntity
from shared.services.nlp.analysis import spacy_model_version
from shared.services.prompt_runner import render_template

logger = logging.getLogger(__name__)

_STATISTICAL_MODEL = "statistisches Modell"

_KIND_LABEL = {
    NerFlagKind.WRONG_LABEL: "Falsches Label",
    NerFlagKind.NOT_AN_ENTITY: "Keine Entität",
    NerFlagKind.MISSED_ENTITY: "Übersehene Entität",
}


class NerAnalysisPromptNotSeededError(RuntimeError):
    """The ner_fehleranalyse prompt has not been seeded into the PromptLibrary."""


class SuggestedRuleOut(BaseModel):
    """The advisory EntityRuler fix the LLM may propose."""

    model_config = ConfigDict(extra="forbid")

    label: str
    pattern: EntityPattern | None = None
    pattern_id: str | None = None


class NerErrorAnalysis(BaseModel):
    """Structured output of the error-analysis prompt."""

    model_config = ConfigDict(extra="forbid")

    reasoning: list[str] = Field(default_factory=list)
    category: NerFailureCategory
    analysis: str
    suggested_rule: SuggestedRuleOut | None = None


def _format_flag(flag: NerFlag) -> str:
    lines = [
        f"Art: {_KIND_LABEL[flag.kind]} ({flag.kind.value})",
        f"Markierter Text: {flag.span_text!r}",
        f"Betroffenes Label: {flag.label}",
    ]
    if flag.expected_label:
        lines.append(f"Erwartetes Label: {flag.expected_label}")
    lines.append(f"Satz: {flag.sentence_text}")
    lines.append(f"Nutzerkommentar: {flag.user_comment}")
    return "\n".join(lines)


def _format_entities(snapshot: list[SnapshotEntity]) -> str:
    if not snapshot:
        return "(keine Entitäten extrahiert)"
    return "\n".join(
        f"- [{entity.label}] {entity.text}  "
        f"(Herkunft: {entity.pattern_id or _STATISTICAL_MODEL})"
        for entity in snapshot
    )


def _format_rules(rules: list[EntityRule]) -> str:
    payload = [
        {"label": rule.label, "pattern": rule.pattern, "pattern_id": rule.pattern_id}
        for rule in rules
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def analyze_flag(flag: NerFlag, *, engine: AsyncEngine, llm: LLMClient) -> NerFlag:
    """Run the error analysis for one flag and persist the result. Returns the updated
    flag; on LLM failure returns the flag unchanged (analysis stays null, retriable)."""
    async with unit_of_work(engine) as uow:
        rules = await uow.entity_rules.list_enabled()
        prompt = await uow.prompt_versions.get_latest(PromptType.NER_FEHLERANALYSE)
    if prompt is None:
        raise NerAnalysisPromptNotSeededError(
            f"no seeded prompt for {PromptType.NER_FEHLERANALYSE.value}"
        )

    spacy_version = spacy_model_version()
    system = render_template(
        prompt.system_prompt,
        {
            "flag": _format_flag(flag),
            "text": flag.source_text,
            "entities": _format_entities(flag.entity_snapshot),
            "spacy_model": spacy_version,
            "entity_rules": _format_rules(rules),
        },
    )
    messages = [
        {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
        {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: "Analysiere den gemeldeten Fehler."},
    ]

    try:
        result, _ = await llm.chat_with_reasoning(
            model=prompt.model_name,
            messages=messages,
            output_model=NerErrorAnalysis,
            temperature=prompt.temperature,
            top_p=prompt.top_p,
            reasoning_effort=prompt.reasoning_effort,
            strict=False,
            chat_prompt_type=prompt.prompt_type.value,
            chat_prompt_version=prompt.version,
        )
    except (LLMError, ValueError, httpx.HTTPError) as exc:
        # LLM-boundary failure (refusal, truncation, bad structured output, transport):
        # the flag (the human observation) survives with a null analysis and can be retried.
        logger.warning("NER error analysis failed for flag %s: %s", flag.ner_flag_uuid, exc)
        return flag

    suggested = (
        result.suggested_rule.model_dump(mode="json") if result.suggested_rule else None
    )
    async with unit_of_work(engine) as uow:
        updated = await uow.ner_flags.update(
            flag.ner_flag_uuid,
            category=result.category.value,
            llm_analysis=result.analysis,
            suggested_rule=suggested,
            llm_model=prompt.model_name,
            prompt_version=prompt.version,
            spacy_model_version=spacy_version,
            analyzed_at=datetime.now(UTC),
        )
    assert updated is not None  # the flag was just persisted by the caller
    return updated
