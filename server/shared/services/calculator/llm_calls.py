"""The THREE places an LLM lives in this agent - nowhere else.

  1. classify_position   -> ClassificationResult   (which registry file?)
  2. resolve_one_driver  -> DriverDecision         (read documents / decide ONE driver)
  3. select_method       -> MethodSelection        (pick the Bauweise per operation)

Everything else in the pipeline is deterministic code. All three sites share the
same contract: structured output with explicit `reasoning` steps, confidence + notes,
and an absolute ban on producing or converting numbers beyond reading values verbatim
from text. Drivers are resolved ONE at a time (a call per driver) so the conversation
reads as a followable chain and later drivers can lean on earlier ones.

Calls go through the shared `LLMClient` (settings.calculator_model over OpenRouter),
which records usage + execution-log telemetry and, via `chat_with_reasoning`, returns
the provider's reasoning summary alongside the validated output. The summary is requested
with settings.calculator_reasoning_effort and is best-effort (None when the model emits
none). Temperature is omitted because the calculator model is a reasoning model. With
settings.calculator_mock the canned-but-realistic replies are returned instead; they are
wired to the FSS demo position (L101 / OZ 01.03.0004).
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
from shared.services.calculator.models import (
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
CLASSIFY_SYSTEM = """\
You are the classification stage of a German road-construction cost-estimation
agent (Kalkulation). You read one LV position (Leistungsverzeichnis) and assign
it to exactly one registered work type (Leistung).

You will be given:
- The position text (OZ, Kurztext, Langtext), usually in German.
- The list of registered work_type codes, each with trigger keywords.
- Optionally: retrieved project context around this position (Baubeschreibung,
  neighbouring positions).

Rules:
1. Choose ONLY from the offered work_type codes. If none fits, answer "unknown".
2. Do not guess from the OZ number alone; the Langtext governs.
3. confidence: 0.9+ only when the text names the Leistung essentially verbatim
   (e.g. "Frostschutzschicht herstellen" -> fss_herstellen). Ambiguity, mixed
   scopes, or unfamiliar wording => 0.7 or below.
4. notes: 1-2 sentences citing the decisive wording, in English with the
   German terms kept verbatim.
5. reasoning: fill FIRST with 2-5 short steps (evidence -> rule -> conclusion),
   in English with the German terms kept verbatim.
6. You classify; you never estimate, compute, or mention costs or quantities.
"""


async def classify_position(
    llm: LLMClient,
    position: dict,
    registry_index: list[dict],
    context_snippets: list[str],
    *,
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
    user = (f"LV position:\n{json.dumps(position, ensure_ascii=False, indent=2)}\n\n"
            f"Registered work types:\n{json.dumps(registry_index, ensure_ascii=False, indent=2)}\n\n"
            f"Retrieved project context:\n"
            f"{json.dumps(context_snippets, ensure_ascii=False, indent=2)}")
    return await llm.chat_with_reasoning(
        model=settings.calculator_model,
        messages=_messages(CLASSIFY_SYSTEM, user),
        output_model=ClassificationResult,
        temperature=None,
        reasoning_effort=settings.calculator_reasoning_effort,
        strict=False,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


# =============================================================================
# PROMPT 2 - DRIVER RESOLUTION  (ONE call per driver; evidence-only)
# =============================================================================
DRIVER_SYSTEM = """\
You are the driver-resolution stage of a German road-construction cost agent. You
resolve ONE driver - a fact the deterministic calculation needs - from the supplied
evidence, never from your own knowledge and never from anything outside the evidence.

You will be given:
- One driver spec: id, source, einheit, decision rule (description) and, for a
  judgment driver, its options.
- The evidence for this driver: for an lv_text driver, the LV position text; for a
  plan/project/judgment driver, excerpts retrieved from the tender documents by
  semantic + keyword search.
- The drivers already resolved earlier this run, for judgment calls that depend on them.

Rules by source:
- lv_text / plan / project: READ the value from the evidence and copy it verbatim
  (convert nothing, compute nothing); put the exact snippet in source_quote. If the
  text's unit differs from einheit, report what the text says and note it - do not convert.
- judgment: choose EXACTLY ONE of the offered options using the evidence and the
  decision rule. The choice IS the value; put your justification in reasoning, not value.
- If the evidence does not contain the value: value null and say why in note. NEVER
  fill a gap with a typical or assumed value.

confidence: direct verbatim read => 0.95+; inferred from context => 0.6-0.8.
reasoning: fill FIRST with 2-5 short steps (evidence -> rule -> conclusion), English
with the German terms kept verbatim.
You extract and decide; you never calculate.
"""

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
    project_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
) -> tuple[DriverDecision, str | None]:
    if settings.calculator_mock:
        decision = _MOCK_DRIVER_DECISIONS.get(spec["id"])
        if decision is None:
            decision = DriverDecision(value=None, confidence=0.0,
                                      note="mock: no canned value for this driver")
        return decision, None
    user = (f"Driver to resolve:\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n\n"
            f"Evidence (use ONLY this):\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n\n"
            f"Drivers already resolved this run:\n"
            f"{json.dumps(resolved, ensure_ascii=False, indent=2, default=str)}")
    return await llm.chat_with_reasoning(
        model=settings.calculator_model,
        messages=_messages(DRIVER_SYSTEM, user),
        output_model=DriverDecision,
        temperature=None,
        reasoning_effort=settings.calculator_reasoning_effort,
        strict=False,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )


# =============================================================================
# PROMPT 3 - METHOD SELECTION  (the Bauweise judgment, per operation)
# =============================================================================
METHOD_SYSTEM = """\
You are the method-selection (Bauweise) stage of a German road-construction
cost agent, deciding HOW one operation will be executed.

You will be given:
- The operation and its candidate methods, each with applicability criteria
  written by the firm's Kalkulatoren.
- The resolved drivers the registry marked relevant for this decision.
- Fleet availability (which machine classes the firm can actually field).
- Retrieved project context and Kalkulator reasoning notes for similar
  situations.

Rules:
1. Choose EXACTLY ONE of the offered method ids. Never invent a method.
2. Apply the criteria to the drivers explicitly: your notes must say which
   criterion matched which driver value (e.g. "strip_width 0.5 m < drum width
   ~1.7 m -> ruettelplatte").
3. A method whose machine_class is unavailable in the fleet needs a strong
   reason to be chosen anyway (e.g. rental noted) - prefer available ones.
4. If no method's criteria fit the drivers, answer "escalate".
5. confidence reflects criteria fit, not eloquence. Conflicting criteria or
   missing drivers => below 0.8 (the run continues; low confidence is batched
   into the final human review, so honesty is cheap and wrong certainty is not).
6. reasoning: fill FIRST with 2-5 short steps applying each candidate's
   criteria to the driver values (evidence -> criterion -> conclusion).
7. You select; you never estimate durations or costs.
"""


async def select_method(
    llm: LLMClient,
    operation: dict,
    drivers: dict,
    fleet: dict,
    notes: list[str],
    *,
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
    user = (f"Operation:\n{json.dumps(operation, ensure_ascii=False, indent=2)}\n\n"
            f"Relevant drivers:\n{json.dumps(drivers, ensure_ascii=False, indent=2)}\n\n"
            f"Fleet availability:\n{json.dumps(fleet, indent=2)}\n\n"
            f"Retrieved context and reasoning notes:\n"
            f"{json.dumps(notes, ensure_ascii=False, indent=2)}")
    return await llm.chat_with_reasoning(
        model=settings.calculator_model,
        messages=_messages(METHOD_SYSTEM, user),
        output_model=MethodSelection,
        temperature=None,
        reasoning_effort=settings.calculator_reasoning_effort,
        strict=False,
        project_uuid=project_uuid,
        conversation_uuid=conversation_uuid,
    )
