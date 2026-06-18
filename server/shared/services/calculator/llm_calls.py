"""The THREE places an LLM lives in this agent - nowhere else.

  1. classify_position   -> ClassificationResult   (which registry file?)
  2. resolve_one_driver  -> DriverDecision         (read documents / decide ONE driver)
  3. select_method       -> MethodSelection        (pick the Bauweise per operation)

Everything else in the pipeline is deterministic code. All three sites share the
same contract: structured output with explicit `reasoning` steps, confidence + notes,
and an absolute ban on producing or converting numbers beyond reading values verbatim
from text. Drivers are resolved ONE at a time (a call per driver) so the conversation
reads as a followable chain and later drivers can lean on earlier ones.

Each site runs on a DB-backed, versioned PromptVersion (PromptType.EKT_CLASSIFY /
EKT_RESOLVE_DRIVER / EKT_SELECT_METHOD, plus EKT_SEED_DRIVERS for the pre-run chat-seed
extractor). The caller resolves the PromptVersion once (shared.services.calculator.prompts)
and passes it in; the model, system prompt, temperature and reasoning effort all come from
it, and prompt_type/version tag the usage + execution log. Calls go through the shared
`LLMClient` over OpenRouter, which records that telemetry and, via `chat_with_reasoning`,
returns the provider's reasoning summary alongside the validated output (best-effort: None
when the model emits none, or when the prompt sets no reasoning effort). With
settings.calculator_mock the canned-but-realistic replies are returned instead (the prompt
is unused); they are wired to the FSS demo position (L101 / OZ 01.03.0004).
"""

from __future__ import annotations

import json
from uuid import UUID

from shared.clients.llm.client import (
    LLMClient,
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
    ROLE_SYSTEM,
    ROLE_USER,
)
from shared.config import settings
from shared.models.prompt_version import PromptVersion
from shared.services.calculator.models import (
    ChatDriverSeeds,
    ClassificationResult,
    DriverDecision,
    MethodSelection,
)


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [
        {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
        {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: user},
    ]


# =============================================================================
# PROMPT 1 - CLASSIFICATION  (gate: low confidence -> HITL interrupt)
# =============================================================================
async def classify_position(
    llm: LLMClient,
    position: dict,
    registry_index: list[dict],
    context_snippets: list[str],
    *,
    prompt: PromptVersion | None = None,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[ClassificationResult, str | None]:
    if settings.calculator_mock:
        return ClassificationResult(
            reasoning=['Langtext opens with "Frostschutzschicht herstellen" - a verbatim '
                       'fss_herstellen trigger.',
                       'Baustoffgemisch 0/32 confirms an unbound ToB layer; no other work '
                       'type fits.'],
            work_type="fss_herstellen", confidence=0.93,
            notes='Langtext opens with "Frostschutzschicht herstellen" and names '
                  'Baustoffgemisch 0/32 - direct match on the fss_herstellen triggers.'), None
    assert prompt is not None  # live mode: the caller always supplies the loaded PromptVersion
    user = (f"LV position:\n{json.dumps(position, ensure_ascii=False, indent=2)}\n\n"
            f"Registered work types:\n{json.dumps(registry_index, ensure_ascii=False, indent=2)}\n\n"
            f"Retrieved project context:\n"
            f"{json.dumps(context_snippets, ensure_ascii=False, indent=2)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=ClassificationResult,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


# =============================================================================
# PROMPT 2 - DRIVER RESOLUTION  (ONE call per driver; evidence-only)
# =============================================================================
# Canned per-driver replies for --mock, wired to the FSS demo position (OZ 01.03.0004).
_MOCK_DRIVER_DECISIONS: dict[str, DriverDecision] = {
    "material_spec": DriverDecision(
        reasoning=['Langtext names "Baustoffgemisch 0/32 ... B2-Material" verbatim.',
                   "Grading 0/32 + class B2 -> catalog key FSS 0/32 B2."],
        value="FSS 0/32 B2",
        source_quote="Baustoffgemisch 0/32 ... B2-Material, gebr. Naturgestein nach "
                     "ZTV-StB LSBB St 21", confidence=0.97),
    "einbaudicke_cm": DriverDecision(
        reasoning=["Langtext states the Einbaudicke directly.", "lv_text: copy verbatim."],
        value=20, source_quote="Einbaudicke '= 20 cm'", confidence=0.97),
    "ev2_target_mpa": DriverDecision(
        reasoning=["Langtext gives the Verformungsmodul target.", "lv_text: copy verbatim."],
        value=45, source_quote="Verdichtungsgrad/Verformungsmodul 'Ev2 = 45 MPa.'",
        confidence=0.97),
    "strip_length_m": DriverDecision(
        reasoning=["Plan excerpt gives the abgerechnete Laenge of the Verbreiterungsstreifen.",
                   "Single Bauphase -> Ausbaulaenge is the full strip length."],
        value=1000, source_quote="plan: Verbreiterungsstreifen, abgerechnete Laenge",
        confidence=0.9),
    "strip_width_m": DriverDecision(
        reasoning=["Streifenbreite cited in the sibling OZ 01.03.0005 Hinweis."],
        value=0.5, source_quote="Streifenbreite >/= 50,0 cm (Hinweis zur OZ 01.03.0005)",
        confidence=0.85),
    "haul_distance_km": DriverDecision(
        reasoning=["Project context names the naechstes Lieferwerk distance."],
        value=12, source_quote="project: naechstes Lieferwerk", confidence=0.8),
    "section_scope": DriverDecision(
        reasoning=["Documents name a single Bauphase for the strip -> single_length."],
        value="single_length", confidence=0.8),
    "access_class": DriverDecision(
        reasoning=["Narrow Verbreiterungsstreifen + Handeinbau hint in sibling OZ 01.03.0005.",
                   "Confined vs open -> confined."],
        value="confined", confidence=0.72),
    "loss_profile": DriverDecision(
        reasoning=["Nichttragfaehige Teilflaechen + narrow strip -> elevated loss vs standard."],
        value="elevated", confidence=0.70),
}


async def resolve_one_driver(
    llm: LLMClient,
    spec: dict,
    evidence: dict,
    resolved: dict,
    *,
    prompt: PromptVersion | None = None,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[DriverDecision, str | None]:
    if settings.calculator_mock:
        decision = _MOCK_DRIVER_DECISIONS.get(spec["id"])
        if decision is None:
            decision = DriverDecision(value=None, confidence=0.0,
                                      note="mock: no canned value for this driver")
        return decision, None
    assert prompt is not None  # live mode: the caller always supplies the loaded PromptVersion
    user = (f"Driver to resolve:\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n\n"
            f"Evidence (use ONLY this):\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n\n"
            f"Drivers already resolved this run:\n"
            f"{json.dumps(resolved, ensure_ascii=False, indent=2, default=str)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=DriverDecision,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


# =============================================================================
# PROMPT 3 - METHOD SELECTION  (the Bauweise judgment, per operation)
# =============================================================================
async def select_method(
    llm: LLMClient,
    operation: dict,
    drivers: dict,
    fleet: dict,
    notes: list[str],
    *,
    prompt: PromptVersion | None = None,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[MethodSelection, str | None]:
    if settings.calculator_mock:
        canned = {
            "distribute": MethodSelection(
                reasoning=["strip_width 0.5 m and access_class confined match the "
                           "loader criteria 'irregular patches, confined or narrow strips'.",
                           "grader_3d is unavailable in the fleet, so the 3D-GNSS grader "
                           "would need rental."],
                method="dozer_loader_grader", confidence=0.78,
                notes="strip_width 0.5 m + access_class confined match 'irregular "
                      "patches, confined or narrow strips'; grader_3d also unavailable "
                      "in fleet."),
            "compact": MethodSelection(
                reasoning=["strip_width 0.5 m is narrower than a roller drum (~1.7 m), "
                           "so the roller criteria fail.",
                           "Plate criteria 'confined strips narrower than a drum' match."],
                method="ruettelplatte", confidence=0.85,
                notes="strip_width 0.5 m < drum width ~1.7 m -> roller criteria fail; "
                      "plate criteria 'confined strips narrower than a drum' match."),
        }
        offered = {m["id"] for m in operation["methods"]}
        sel = canned.get(operation["id"])
        if sel is not None and sel.method in offered:
            return sel, None
        return MethodSelection(method=operation["methods"][0]["id"], confidence=0.9,
                               notes="mock: first offered method"), None
    assert prompt is not None  # live mode: the caller always supplies the loaded PromptVersion
    user = (f"Operation:\n{json.dumps(operation, ensure_ascii=False, indent=2)}\n\n"
            f"Relevant drivers:\n{json.dumps(drivers, ensure_ascii=False, indent=2)}\n\n"
            f"Fleet availability:\n{json.dumps(fleet, indent=2)}\n\n"
            f"Retrieved context and reasoning notes:\n"
            f"{json.dumps(notes, ensure_ascii=False, indent=2)}")
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=MethodSelection,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


# =============================================================================
# PRE-STEP - CHAT DRIVER SEEDS  (lift explicit driver values from the pre-run chat)
# =============================================================================
async def extract_chat_drivers(
    llm: LLMClient,
    transcript: list[dict],
    driver_catalog: list[dict],
    *,
    prompt: PromptVersion | None = None,
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> ChatDriverSeeds:
    if settings.calculator_mock:
        return ChatDriverSeeds(assignments=[])
    assert prompt is not None  # live mode: the caller always supplies the loaded PromptVersion
    user = (f"Conversation transcript:\n{json.dumps(transcript, ensure_ascii=False, indent=2)}\n\n"
            f"Driver catalog (choose ids ONLY from here):\n"
            f"{json.dumps(driver_catalog, ensure_ascii=False, indent=2)}")
    # strict=False (Pydantic-validated): matches the other calculator sites; OpenAI/Azure reject a
    # strict json_schema that isn't all-required + additionalProperties:false. The seed prompt sets
    # no reasoning effort, so no reasoning summary is requested.
    seeds, _ = await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=ChatDriverSeeds,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )
    return seeds
