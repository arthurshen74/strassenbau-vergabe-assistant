"""The THREE places an LLM lives in this agent - nowhere else.

  1. classify_position   -> ClassificationResult   (which registry file?)
  2. resolve_drivers     -> DriverResolution       (read documents, decide judgment drivers)
  3. select_method       -> MethodSelection        (pick the Bauweise per operation)

Everything else in the pipeline is deterministic code. All three sites share
the same contract: structured output with explicit `reasoning` steps, confidence
+ notes, and an absolute ban on producing or converting numbers beyond reading
values verbatim from text.

Calls go to OpenRouter (settings.calculator_model) as structured outputs and
return a (result, provider_reasoning) tuple. The provider's reasoning summary
is requested via settings.calculator_reasoning_effort and captured from the raw
HTTP body with an httpx response hook, because langchain-openai drops
OpenRouter's non-standard `message.reasoning` field during parsing. With
settings.calculator_mock the canned-but-realistic replies are returned instead;
they are wired to the FSS demo position (L101 / OZ 01.03.0004).
"""

from __future__ import annotations

import json
from typing import TypeVar

import httpx
from langchain_core.utils import convert_to_secret_str
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from shared.config import settings
from shared.services.calculator.models import (
    ClassificationResult,
    DriverResolution,
    DriverValue,
    MethodSelection,
)

# The ChatOpenAI base_url is the chat-completions URL without its endpoint suffix; one
# settings value is the source of truth for the OpenRouter host.
_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"

T = TypeVar("T", bound=BaseModel)


class _ReasoningCapture:
    """httpx response hook that lifts OpenRouter's `message.reasoning` summary
    from the raw chat-completions body (best-effort; absent on error bodies and
    on models that return no reasoning)."""

    def __init__(self) -> None:
        self.reasoning: str | None = None

    async def __call__(self, response: httpx.Response) -> None:
        await response.aread()
        try:
            message = response.json()["choices"][0]["message"]
        except (ValueError, LookupError):
            return
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            self.reasoning = reasoning.strip()


async def _ainvoke(schema: type[T], messages: list[tuple[str, str]]) -> tuple[T, str | None]:
    capture = _ReasoningCapture()
    extra_body = {}
    if settings.calculator_reasoning_effort is not None:
        # summary "detailed" nudges OpenAI models to emit a summary; even so the
        # field is null whenever the model produces no summarizable reasoning.
        extra_body["reasoning"] = {"effort": settings.calculator_reasoning_effort,
                                   "summary": "detailed"}
    async with httpx.AsyncClient(event_hooks={"response": [capture]}) as http_client:
        model = ChatOpenAI(
            model=settings.calculator_model,
            base_url=settings.openrouter_api_url_chat.removesuffix(_CHAT_COMPLETIONS_SUFFIX),
            api_key=convert_to_secret_str(settings.openrouter_api_key or ""),
            extra_body=extra_body,
            http_async_client=http_client,
        )
        result = await model.with_structured_output(
            schema, method="function_calling"
        ).ainvoke(messages)
    return result, capture.reasoning


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
    position: dict, registry_index: list[dict], context_snippets: list[str]
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
    return await _ainvoke(ClassificationResult,
                          [("system", CLASSIFY_SYSTEM), ("user", user)])


# =============================================================================
# PROMPT 2 - DRIVER RESOLUTION  (extraction + judgment drivers, flagged)
# =============================================================================
DRIVERS_SYSTEM = """\
You are the driver-resolution stage of a German road-construction cost agent.
The registry for this work type defines the drivers (facts) the deterministic
calculation needs. Your job is to fill them from the documents - never from
your own knowledge.

You will be given:
- The driver specs: id, source, einheit, and (for judgment drivers) options.
- The LV position text.
- Per-driver retrieved project context (plan and Baubeschreibung excerpts,
  found by semantic search over the tender documents).

Rules per driver, by its `source`:
- lv_text / plan / project: READ the value from the matching document. Copy it
  as written (convert nothing, compute nothing). Put the verbatim snippet in
  source_quote. If the unit in the text differs from the requested einheit,
  report what the text says and flag it - do not convert.
- judgment: choose EXACTLY ONE of the offered options, using the documents and
  the retrieved context. Explain nothing in the value; the choice IS the value.
  These are judgment calls - be honest in confidence.
- Anything you cannot find: value null, and add a human-readable entry to
  flags. NEVER fill a gap with a typical or assumed value.

confidence: per driver. Direct verbatim read => 0.95+. Inferred from context
(e.g. deriving access_class from strip width + Handeinbau hints) => 0.6-0.8.
reasoning: fill FIRST with 2-5 short steps covering the non-obvious reads and
every judgment call (evidence -> rule -> conclusion).
You extract and decide; you never calculate.
"""


async def resolve_drivers(
    driver_specs: list[dict], context: dict
) -> tuple[DriverResolution, str | None]:
    if settings.calculator_mock:
        return DriverResolution(
            reasoning=["Material, Dicke and Ev2 read verbatim from the Langtext.",
                       "Strip geometry comes from the plan excerpt; width is cited in the "
                       "sibling OZ 01.03.0005 Hinweis.",
                       "Narrow strip + Handeinbau hint + nichttragfaehige Teilflaechen -> "
                       "confined access and elevated loss."],
            drivers=[
            DriverValue(id="material_spec", value="FSS 0/32 B2", einheit="text",
                        source_quote="Baustoffgemisch 0/32 ... B2-Material, gebr. Naturgestein "
                                     "nach ZTV-StB LSBB St 21", confidence=0.97),
            DriverValue(id="einbaudicke_cm", value=20, einheit="cm",
                        source_quote="Einbaudicke '= 20 cm'", confidence=0.97),
            DriverValue(id="ev2_target_mpa", value=45, einheit="MPa",
                        source_quote="Verdichtungsgrad/Verformungsmodul 'Ev2 = 45 MPa.'",
                        confidence=0.97),
            DriverValue(id="strip_length_m", value=1000, einheit="m",
                        source_quote="plan: Verbreiterungsstreifen, abgerechnete Laenge",
                        confidence=0.9),
            DriverValue(id="strip_width_m", value=0.5, einheit="m",
                        source_quote="Streifenbreite >/= 50,0 cm (Hinweis zur OZ 01.03.0005)",
                        confidence=0.85),
            DriverValue(id="haul_distance_km", value=12, einheit="km",
                        source_quote="project: naechstes Lieferwerk", confidence=0.8),
            DriverValue(id="ambient_temp_c", value=16.0, einheit="degC",
                        source_quote="tool:climate normals, build window", confidence=0.9),
            DriverValue(id="access_class", value="confined", confidence=0.72),
            DriverValue(id="loss_profile", value="elevated", confidence=0.70),
        ], flags=["access_class and loss_profile are judgment calls: narrow "
                  "Verbreiterungsstreifen + Handeinbau hint in sibling OZ 01.03.0005 "
                  "+ nichttragfaehige Teilflaechen -> confined access, elevated loss."]), None
    user = (f"Driver specs:\n{json.dumps(driver_specs, ensure_ascii=False, indent=2)}\n\n"
            f"Context documents:\n{json.dumps(context, ensure_ascii=False, indent=2)}")
    return await _ainvoke(DriverResolution,
                          [("system", DRIVERS_SYSTEM), ("user", user)])


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


async def select_method(operation: dict, drivers: dict, fleet: dict,
                        notes: list[str]) -> tuple[MethodSelection, str | None]:
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
    return await _ainvoke(MethodSelection,
                          [("system", METHOD_SYSTEM), ("user", user)])
