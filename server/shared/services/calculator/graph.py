# pyright: reportTypedDictNotRequiredAccess=false
"""LangGraph wiring for the EKT position-calculation agent (kalkulation_v2 engine).

Topology (ARCHITECTURE §7; CALCULATOR_GATE_FLOW_PLAN), four HITL gates, each consuming only
inputs the human already confirmed:
  launch -> extract_chat_values (also harvests project-global candidates)
  -> load_project_context (resolve/reconcile the project globals)
  -> project_context_review (GATE 1: confirm/override the project globals)
  -> classify_leistung (Leistung + Bauverfahren candidates only)
  -> leistung_bv_review (GATE 2: confirm Leistung, select Bauverfahren)
  -> resolve_material (BM25-propose the Baustoff for the confirmed recipe; skipped if none needed)
  -> material_review (GATE 3: confirm the acquisition Baustoff; skipped for material-free recipes)
  -> rank_lieferanten (rank suppliers for the CONFIRMED Baustoff at the confirmed Baustelle)
  -> bind_resources (right-size a machine per slot) -> bind_lieferant (cheapest supplier default)
  -> derive_required_variables -> resolve_variables (merge globals + machine/supplier as proposals)
  -> variable_review (GATE 4: machines + supplier picker + accept/override every leaf, tiered)
  -> compute (deterministic kalkuliere; injects the deponie distance + strip geometry fallback)
  -> render_output

Determinism contract:
  - LANGTEXT/RAG/HITL fill `ctx.werte` (the agent's job, BEFORE calc); the engine
    resolves FORMEL/STAMMDATEN/KONSTANTE deterministically.
  - Every resolved value carries provenance (quelle/konfidenz/beleg) into the
    Nachweistabelle.

Resolution precedence per variable (resolve_variables): chat-pinned (source 0) wins;
otherwise an extracted input runs its catalog cascade LANGTEXT -> RAG -> DEFAULT
(KONSTANTE), and rates/Stammdaten are catalog lookups shown for transparency.

Mock mode (`settings.calculator_mock`): the LLM/RAG seams — chat extraction, Leistung
classification, value extraction, narration — use deterministic stubs so the whole
flow (both gates, real compute) runs offline; the live sites are in `llm_calls`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal, InvalidOperation
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from shared.clients.llm.client import LLMClient
from shared.config import settings
from shared.models.enums import PromptType, RetrievalModality
from shared.models.prompt_version import PromptVersion
from shared.services.calculator import llm_calls
from shared.services.calculator.lieferant_ranking import (
    LieferantAngebot,
    rang_lieferanten,
)
from shared.services.calculator.state import (
    DEFAULT_REVIEW_SCHWELLE,
    RECONCILE_BESTAETIGEN,
    RECONCILE_KONFLIKT,
    RECONCILE_UEBERSCHREIBEN,
    STAGE_LEISTUNG_BV_REVIEW,
    STAGE_MATERIAL_REVIEW,
    STAGE_PROJECT_CONTEXT_REVIEW,
    STAGE_VARIABLE_REVIEW,
    STATUS_AKZEPTIERT,
    STATUS_UEBERSCHRIEBEN,
    TIER_COLLAPSED,
    TIER_SURFACED,
    EKTZeile,
    KostenLinie,
    NachweisZeile,
    PositionKalkulationState,
    VariablenVorschlag,
    wert_from_json,
    wert_to_json,
)
from shared.services.kalkulation_v2.globale_variablen import (
    GLOBAL_VAR_NAMES,
    GLOBALE_VARIABLEN,
    fehlende_erforderliche,
    VAR_DEPONIE_LOCATION,
    VAR_ENTFERNUNG_DEPONIE_KM,
    VAR_FRAESGUT_KLASSE,
    VAR_STRIP_LENGTH_M,
    VAR_STRIP_WIDTH_M,
    ZIEL_FLAECHE_M2,
    ZIEL_FRAESGUT_KLASSE,
    ZIEL_LAENGE_M,
)
from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN
from shared.services.kalkulation_v2.baustoff_suche import suche_baustoff
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.binden import rezept_maschinen_werte
from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN
from shared.services.kalkulation_v2.maschinen import (
    MASCHINEN,
    maschinen_fuer,
    maschinen_sortiert,
)
from shared.services.kalkulation_v2.leistung_bauverfahren import kandidaten, waehle_bauverfahren
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.materialien import BAUSTOFFE
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M,
    Baustoff,
    Kalkulationskontext,
    Kalkulator,
    VariableDefinition,
    VariablenWert,
)
from shared.services.kalkulation_v2.store import (
    FORMELN,
    GEOM,
    KATALOG,
    STICHTAG,
    kalkuliere_kontext,
)
from shared.services.kalkulation_v2.worklist import (
    BlattArt,
    benoetigte_variablen,
    braucht_baustoff,
)
from shared.services.retrieval.config import RetrievalConfig

# Async `query -> formatted evidence snippets` callable; None runs without retrieval.
ContextRetriever = Callable[[str], Awaitable[list[str]]]

# Project-context seams (run_service injects DB + retrieval + persistence; None in standalone
# tests). The loader resolves/persists the missing globals and reconciles the chat candidates;
# the saver persists a review override. Both keep DB/retrieval out of the pure graph.
#   loader(project_uuid, chat_global_kandidaten) -> {"projekt_kontext": flat, "reconcile": flags}
#   saver(project_uuid, update_fields)           -> updated flat projekt_kontext
ProjectContextLoader = Callable[[UUID, dict], Awaitable[dict]]
ProjectContextSaver = Callable[[UUID, dict], Awaitable[dict]]

# The calculator's retrieval policy: hybrid dense + BM25 fused by RRF, multi-question
# expansion, cross-encoder rerank, PLUS scope (project documents + the LV).
CALCULATOR_RETRIEVAL_CONFIG = RetrievalConfig(
    modality=RetrievalModality.PLUS,
    multi_query=True,
    use_bm25=True,
    use_cross_encoder=True,
)

# Position dict key carrying the test/CLI Leistung hint the mock classifier honours.
POSITION_LEISTUNG_HINT = "leistung_hint"

# reasoning_log entry kinds: deterministic narration, the LLM's structured steps,
# and the provider's raw reasoning summary (best-effort).
REASONING_NARRATION = "narration"
REASONING_LLM = "llm"
REASONING_PROVIDER = "provider"

PROVENANCE_CHAT = "aus Chat (Kalkulator)"
PROVENANCE_DEFAULT = "Standardwert (Katalog)"
PROVENANCE_OVERRIDE = "Gate B (Kalkulator)"

# The supplier-filled inbound haul-distance variable (Antransport); bind_lieferant resolves it.
LIEFERANT_DISTANCE_VAR = "entfernung_lieferant_km"
# STAMMDATEN beleg prefix every material price bridge shares (all read baustoff.basispreis*).
STAMMDATEN_PREIS_PRAEFIX = "baustoff.basispreis"

# The catalog-derived label spaces and gate payloads below are computed per use, never at module
# level: this module is imported before `lade_katalog` refills the engine dicts at startup, and an
# activation refills them again mid-process — an import-time snapshot would pin the fixture
# catalog for the process lifetime. The lists are tiny; rebuilding per use is negligible.


def leistung_index() -> list[dict]:
    """Leistung label space for the classification prompt."""
    return [{"leistung_key": k, "name": v.name, "standard_kennung": v.standard_kennung}
            for k, v in LEISTUNGEN.items()]


def chat_katalog() -> list[dict]:
    """Per-position engine variables targeted by chat extraction."""
    return [{"name": n, "bezeichnung": d.bezeichnung, "einheit": d.einheit}
            for n, d in KONTEXT_VARIABLEN.items()]


def chat_katalog_mit_global() -> list[dict]:
    """Chat extraction also targets the project globals, so values the Kalkulator already stated
    in chat ("die Deponie ist in Sangerhausen", "der Abschnitt ist 5,1 km") are captured as global
    candidates (the load_project_context node reconciles them against the saved/resolved values)."""
    return chat_katalog() + [{"name": g.name, "bezeichnung": g.bezeichnung, "einheit": g.einheit}
                             for g in GLOBALE_VARIABLEN.values()]


def chat_global_names() -> frozenset[str]:
    """Globals captured from chat as project candidates are only those that are NOT also
    per-position engine variables. fraesgut_klasse is both a global and a KATALOG variable; a chat
    statement about it is a per-position input (precedence §3: per-position input > project
    global), so it stays in chat_werte and is not reconciled as a project candidate."""
    return frozenset(n for n in GLOBAL_VAR_NAMES if n not in KATALOG)


def leistung_katalog() -> list[dict]:
    """Full Leistung -> candidate Bauverfahren map for the Gate A method-review UI, so the
    Kalkulator can correct the classification and pick a recipe even when the position did not
    classify cleanly."""
    return [{"leistung_key": k, "name": v.name, "kandidaten": kandidaten(k)}
            for k, v in LEISTUNGEN.items()]


def _bv_slots(bauverfahren) -> list[str]:
    return list(dict.fromkeys(vg.ausfuehrungsart.code for vg in bauverfahren.vorgaenge
                              if vg.ausfuehrungsart is not None and maschinen_fuer(vg.ausfuehrungsart.code)))


def bauverfahren_ressourcen() -> dict[str, list[dict]]:
    """Per-Bauverfahren machine slots + candidates, so Gate A can offer a machine picker per slot
    once a recipe is chosen. Only slots with >=1 catalog machine are pickable."""
    aa_by_code = {a.code: a for a in AUSFUEHRUNGSARTEN.values()}
    return {
        bv_code: [
            {"slot": slot, "geraet": aa_by_code[slot].name,
             "kandidaten": [{"code": m.code, "hersteller": m.hersteller, "modell": m.modell}
                            for m in maschinen_fuer(slot)]}
            for slot in _bv_slots(bv)
        ]
        for bv_code, bv in BAUVERFAHREN.items()
    }


def baustoff_katalog() -> list[dict]:
    """Baustoff catalog for the Gate 3 material picker (offered optionally; most positions
    need none)."""
    return [{"code": b.code, "name": b.name, "kategorie": b.kategorie}
            for b in BAUSTOFFE.values()]

# First numeric token in a verbatim read, e.g. "ca. 0,30" or "über 3 bis 4,5 cm".
_NUMERIC_TOKEN = re.compile(r"-?\d+(?:[.,]\d+)?")

logger = logging.getLogger(__name__)

_writer_unavailable_warned = False


def _write_live(entry: dict) -> None:
    """Emit one reasoning entry to the custom stream so the UI sees it mid-node. No-op
    when the run isn't streaming with custom mode (CLI / ainvoke)."""
    global _writer_unavailable_warned
    try:
        writer = get_stream_writer()
    except RuntimeError:
        if not _writer_unavailable_warned:
            logger.warning(
                "calculator stream writer unavailable; live reasoning deltas will not "
                "stream. Expected only for CLI/ainvoke, not an SSE run."
            )
            _writer_unavailable_warned = True
        return
    writer(entry)


def reason(stage: str, kind: str, text: str) -> dict:
    entry = {"stage": stage, "kind": kind, "text": text}
    _write_live(entry)
    return entry


def reason_llm(stage: str, steps: list[str], provider: str | None) -> list[dict]:
    entries = [reason(stage, REASONING_LLM, step) for step in steps]
    if provider:
        entries.append(reason(stage, REASONING_PROVIDER, provider))
    return entries


# --------------------------------------------------------- catalog helpers --
def _konstante_wert(defn: VariableDefinition) -> Decimal | None:
    """The KONSTANTE fallback value in a variable's cascade (rate-book value, or the
    mit_default fallback), or None when the cascade has none."""
    for schritt in defn.aufloesung:
        if schritt.methode == M.KONSTANTE and schritt.konstante is not None:
            return schritt.konstante
    return None


def _stammdaten_wert(defn: VariableDefinition, baustoff: Baustoff | None) -> Decimal | None:
    """Resolve a STAMMDATEN leaf's value off the (effective) Baustoff, for display."""
    if baustoff is None:
        return None
    for schritt in defn.aufloesung:
        if schritt.methode == M.STAMMDATEN and schritt.stammdaten_pfad:
            _, *rest = schritt.stammdaten_pfad.split(".")
            obj: object = baustoff
            for attr in rest:
                obj = getattr(obj, attr, None)
            return obj if isinstance(obj, Decimal) else None
    return None


def _effektiver_baustoff(baustoff_code: str | None, werkspreis: str | None) -> Baustoff | None:
    """The chosen Baustoff with the supplier ex-works price applied when a supplier is bound. The
    single basispreis override flows through every STAMMDATEN price bridge (all read basispreis_eur),
    so both the Gate B proposals and compute see the supplier price with no per-variable wiring."""
    if not baustoff_code:
        return None
    baustoff = BAUSTOFFE.get(baustoff_code)
    if baustoff is None:
        return None
    if werkspreis:
        preis = Decimal(werkspreis)
        return baustoff.model_copy(update={"basispreis_eur": preis, "basispreis_eur_pro_t": preis})
    return baustoff


def _coerce_decimal(value: object) -> Decimal | None:
    """Deterministically parse a verbatim read to Decimal (German comma, leading noise)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    match = _NUMERIC_TOKEN.search(str(value))
    if not match:
        return None
    try:
        return Decimal(match.group().replace(",", "."))
    except InvalidOperation:
        return None


def _parse_override(value: object) -> Decimal | None:
    """Parse a HITL override value into a Decimal. Accepts German convention (',' decimal,
    '.' thousands) as well as the dot-decimal form the proposal is pre-filled with; returns
    None when the input is not a number so the caller can warn instead of crashing."""
    token = str(value).strip()
    if "," in token:                            # German: '.' groups thousands, ',' is the point
        token = token.replace(".", "").replace(",", ".")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


# --------------------------------------------------- proposal builders ------
def _eingabe_vorschlag(name: str, defn: VariableDefinition, hochrisiko: bool, schwelle: float,
                       wert: Decimal, quelle: M, konfidenz: float | None,
                       beleg: str | None) -> VariablenVorschlag:
    niedrig = konfidenz is not None and konfidenz < schwelle
    return VariablenVorschlag(
        name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit,
        art=BlattArt.EINGABE.value, hochrisiko=hochrisiko,
        tier=TIER_SURFACED if (hochrisiko or niedrig) else TIER_COLLAPSED,
        wert=str(wert), quelle=quelle.value,
        konfidenz=None if konfidenz is None else str(konfidenz), beleg=beleg)


def _unresolved_vorschlag(name: str, defn: VariableDefinition, hochrisiko: bool) -> VariablenVorschlag:
    return VariablenVorschlag(
        name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit,
        art=BlattArt.EINGABE.value, hochrisiko=hochrisiko, tier=TIER_SURFACED,
        wert=None, quelle=None, beleg=None)


def _catalog_vorschlag(name: str, art: str, hochrisiko: bool, chat_werte: dict,
                       baustoff: Baustoff | None) -> VariablenVorschlag | None:
    """Proposal for a chat-pinned / SATZ / STAMMDATEN leaf (shared mock + live). Returns
    None for an unpinned EINGABE leaf, which the caller resolves (cascade or mock default)."""
    defn = KATALOG[name]
    if name in chat_werte:
        wj = chat_werte[name]
        return VariablenVorschlag(
            name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit, art=art,
            hochrisiko=hochrisiko, tier=TIER_SURFACED if hochrisiko else TIER_COLLAPSED,
            wert=wj["wert"], quelle=wj["quelle"], konfidenz="1.0", beleg=wj["beleg"])
    if art == BlattArt.SATZ.value:
        konst = _konstante_wert(defn)
        return VariablenVorschlag(
            name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit, art=art,
            hochrisiko=False, tier=TIER_COLLAPSED,
            wert=None if konst is None else str(konst), quelle=M.KONSTANTE.value, beleg=None)
    if art == BlattArt.STAMMDATEN.value:
        val = _stammdaten_wert(defn, baustoff)
        return VariablenVorschlag(
            name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit, art=art,
            hochrisiko=False, tier=TIER_COLLAPSED,
            wert=None if val is None else str(val), quelle=M.STAMMDATEN.value, beleg=None)
    return None


def _slot_betriebsart(bauverfahren, slot: str) -> str | None:
    """The Betriebsart of the recipe's first Vorgang on a slot (its productivity profile)."""
    return next((vg.betriebsart_code for vg in bauverfahren.vorgaenge
                 if vg.ausfuehrungsart is not None and vg.ausfuehrungsart.code == slot
                 and vg.betriebsart_code), None)


def _route_after_leistung_bv(state: PositionKalkulationState) -> str:
    return END if state.get("abgebrochen") else "resolve_material"


def _route_after_resolve_material(state: PositionKalkulationState) -> str:
    # A recipe that needs a material got a proposal (even if the code is None -> pick at Gate 3);
    # a material-free recipe got none, so skip Gate 3 and go straight to supplier ranking (a no-op).
    return "material_review" if state.get("baustoff_vorschlag") is not None else "rank_lieferanten"


def _route_after_material(state: PositionKalkulationState) -> str:
    return END if state.get("abgebrochen") else "rank_lieferanten"


def _erforderlich_fehler(fehlend: list[str]) -> str:
    """Human message naming the required globals that are not yet validly resolved."""
    namen = ", ".join(GLOBALE_VARIABLEN[n].bezeichnung for n in fehlend)
    return f"Pflichtangabe fehlt oder nicht lokalisierbar: {namen}."


def _nachweis(ctx: Kalkulationskontext, preis_beleg: str | None = None) -> list[NachweisZeile]:
    """Render `ctx.werte` (every variable the calc touched) as the derivation tree. When a supplier
    is bound, `preis_beleg` re-labels whichever STAMMDATEN price bridge the recipe used (they all
    read baustoff.basispreis*) so the audit shows the supplier, not the generic catalog path."""
    zeilen: list[NachweisZeile] = []
    for name, w in ctx.werte.items():
        defn = KATALOG.get(name)
        formel = FORMELN.get(name) if w.quelle == M.FORMEL else None
        beleg = w.beleg
        if preis_beleg and w.quelle == M.STAMMDATEN and (w.beleg or "").startswith(STAMMDATEN_PREIS_PRAEFIX):
            beleg = preis_beleg
        zeilen.append(NachweisZeile(
            name=name,
            bezeichnung=defn.bezeichnung if defn else None,
            wert=w.wert,
            einheit=defn.einheit if defn else None,
            quelle=w.quelle.value,
            beleg=beleg,
            ausdruck=formel.ausdruck if formel else None,
            eingaben=sorted(formel.eingaben()) if formel else None,
        ))
    return zeilen


def _projekt_werte(kontext: Mapping[str, object]) -> dict[str, dict]:
    """Engine-variable values sourced from the confirmed project globals, as Gate-B-overridable
    proposals (precedence §3: per-position input > project global > catalog default). The strip
    dims source `laenge_m`/`flaeche_m2` only as a fallback: they apply solely to a leaf still on
    the worklist (a booked geometry is pruned before this merge, and compute books it last, §9)."""
    out: dict[str, dict] = {}
    # The globals are user-confirmed strings that may still carry a unit ("7.5 meters"); parse the
    # numeric token defensively so a stray unit never crashes compute.
    ent = _coerce_decimal(kontext.get(VAR_ENTFERNUNG_DEPONIE_KM))
    if ent is not None:
        deponie = kontext.get(VAR_DEPONIE_LOCATION) or "Deponie"
        out[VAR_ENTFERNUNG_DEPONIE_KM] = wert_to_json(VariablenWert(
            name=VAR_ENTFERNUNG_DEPONIE_KM, wert=ent, quelle=M.STAMMDATEN,
            beleg=f"Baustelle → Deponie {deponie}, {ent} km (Google Routes)"))
    fk = _coerce_decimal(kontext.get(VAR_FRAESGUT_KLASSE))
    if fk is not None:
        out[ZIEL_FRAESGUT_KLASSE] = wert_to_json(VariablenWert(
            name=ZIEL_FRAESGUT_KLASSE, wert=fk, quelle=M.STAMMDATEN,
            beleg="Projektkontext (Fräsgutklasse)"))
    sl = _coerce_decimal(kontext.get(VAR_STRIP_LENGTH_M))
    sw = _coerce_decimal(kontext.get(VAR_STRIP_WIDTH_M))
    if sl is not None:
        out[ZIEL_LAENGE_M] = wert_to_json(VariablenWert(
            name=ZIEL_LAENGE_M, wert=sl, quelle=M.STAMMDATEN,
            beleg=f"Projektkontext: Streckenlänge {sl} m"))
        if sw is not None:
            out[ZIEL_FLAECHE_M2] = wert_to_json(VariablenWert(
                name=ZIEL_FLAECHE_M2, wert=(sl * sw),
                quelle=M.STAMMDATEN, beleg=f"Projektkontext: {sl} m × {sw} m"))
    return out


def _reconcile_global(kontext: Mapping[str, object], kandidaten: Mapping[str, dict]) -> dict:
    """Per chat-stated global, classify it against the saved/resolved value: bestaetigen (agrees
    or none stated), ueberschreiben (chat proposes where none saved), or konflikt (differs)."""
    out: dict = {}
    for name, cand in kandidaten.items():
        chat_wert = cand.get("wert")
        aktuell = kontext.get(name)
        if not aktuell:
            flag = RECONCILE_UEBERSCHREIBEN
        elif str(aktuell).strip() == str(chat_wert).strip():
            flag = RECONCILE_BESTAETIGEN
        else:
            flag = RECONCILE_KONFLIKT
        out[name] = {"flag": flag, "chat_wert": chat_wert, "aktuell_wert": aktuell}
    return out


# ------------------------------------------------------------------- build --
def build_graph(
    retriever: ContextRetriever | None,
    llm: LLMClient | None = None,
    prompts: Mapping[PromptType, PromptVersion] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    project_context_loader: ProjectContextLoader | None = None,
    project_context_saver: ProjectContextSaver | None = None,
):
    """Compile the position-calculation graph. The LLM/RAG nodes close over `retriever`,
    `llm` and `prompts`; all three are unused in mock mode (`settings.calculator_mock`),
    so they may be None there. `project_context_loader`/`project_context_saver` carry the project
    globals (resolve/reconcile + the review override); when both are None the graph skips the
    pre-Gate-A project-context gate and uses any pre-seeded `projekt_kontext` (standalone tests).
    `checkpointer` persists state across the HITL interrupts (defaults to an in-process MemorySaver;
    the conversation service injects Postgres)."""
    prompts = prompts or {}
    kalk = Kalkulator(KATALOG, FORMELN)

    def _baustoff_match(kandidaten_bv: list[str], pos: dict) -> dict | None:
        """BM25-match the LV text to a Baustoff, but only for recipes that consume one.
        Returns the Gate A pre-fill (top hit + alternates + auto flag), or None if the
        default recipe needs no Baustoff. `auto` gates the threshold; below it the picker
        surfaces the hit for confirmation (HITL)."""
        if not kandidaten_bv or not braucht_baustoff(BAUVERFAHREN[kandidaten_bv[0]], kalk):
            return None
        match = suche_baustoff(f"{pos.get('kurztext') or ''} {pos.get('langtext') or ''}")
        top = match.top
        auto = top is not None and match.konfidenz >= settings.calculator_baustoff_match_threshold
        return {
            "code": top.code if top else None,
            "name": top.name if top else None,
            "konfidenz": match.konfidenz,
            "auto": auto,
            "treffer": [t.model_dump() for t in match.treffer],
        }

    async def retrieve(query: str) -> list[str]:
        return await retriever(query) if retriever is not None else []

    async def _resolve_eingabe(name: str, hochrisiko: bool, schwelle: float, position: dict,
                               state: PositionKalkulationState) -> tuple[VariablenVorschlag, list[dict]]:
        """Run one extracted input's catalog cascade: LANGTEXT -> RAG -> DEFAULT, stopping
        at the first accepted step (>= the step's confidence threshold)."""
        defn = KATALOG[name]
        extract_prompt = prompts[PromptType.EKT_LANGTEXT_EXTRACT]
        meta = {"name": name, "bezeichnung": defn.bezeichnung, "einheit": defn.einheit}
        kwargs = {"project_uuid": state.get("project_uuid"),
                  "conversation_uuid": state.get("conversation_uuid")}
        log: list[dict] = []
        for schritt in defn.aufloesung:
            schwelle_step = float(schritt.konfidenz_schwelle or 0)
            if schritt.methode in (M.LANGTEXT, M.RAG):
                if schritt.methode == M.LANGTEXT:
                    evidence = {"langtext": position.get("langtext"),
                                "hinweis": position.get("hinweis")}
                else:
                    intent = schritt.prompt or f"{defn.bezeichnung} {position.get('kurztext', '')}"
                    evidence = {"snippets": await retrieve(intent)}
                ext, prov = await llm_calls.extract_value(
                    llm, {**meta, "anweisung": schritt.prompt}, evidence,
                    prompt=extract_prompt, **kwargs)
                log += reason_llm("resolve_variables", ext.reasoning, prov)
                val = _coerce_decimal(ext.wert) if ext.gefunden else None
                if val is not None and ext.konfidenz >= schwelle_step:
                    log.append(reason("resolve_variables", REASONING_NARRATION,
                                      f"{name} = {val} ({schritt.methode.value}, "
                                      f"Konfidenz {ext.konfidenz:.2f})."))
                    return _eingabe_vorschlag(name, defn, hochrisiko, schwelle, val,
                                              schritt.methode, ext.konfidenz, ext.beleg), log
            elif schritt.methode == M.KONSTANTE and schritt.konstante is not None:
                log.append(reason("resolve_variables", REASONING_NARRATION,
                                  f"{name}: Standardwert {schritt.konstante} verwendet."))
                return _eingabe_vorschlag(name, defn, hochrisiko, schwelle, schritt.konstante,
                                          M.KONSTANTE, None, PROVENANCE_DEFAULT), log
            # M.HITL is a no-op here: it marks "ask a human", but a KONSTANTE fallback may
            # follow it (mit_default). The actual human ask is the Gate B review below.
        log.append(reason("resolve_variables", REASONING_NARRATION,
                          f"{name}: nicht aufgelöst -> zur Prüfung vorgelegt."))
        return _unresolved_vorschlag(name, defn, hochrisiko), log

    # ------------------------------------------------------------- nodes ---
    def launch(state: PositionKalkulationState) -> dict:
        pos = state["position"]
        return {
            "konfidenz_schwelle_review": state.get(
                "konfidenz_schwelle_review", DEFAULT_REVIEW_SCHWELLE),
            "reasoning_log": [
                reason("launch", REASONING_NARRATION,
                       f"Kalkulation gestartet für Position {pos['oz']}: {pos['kurztext']}."),
            ],
        }

    async def extract_chat_values(state: PositionKalkulationState) -> dict:
        """Source 0: harvest values the Kalkulator already stated pre-launch and lock them. Splits
        into per-position values (`chat_werte`) and project-global candidates (`chat_global_kandidaten`,
        reconciled later). Mock reads `vorgaben`/`globale_vorgaben`; live runs the chat-extraction
        prompt over `chat_verlauf` against the combined catalog."""
        chat_werte: dict = {}
        chat_global: dict = {}
        chat_globals = chat_global_names()
        log = [reason("extract_chat_values", REASONING_NARRATION,
                      "Prüfe den Chatverlauf auf bereits genannte Werte (Quelle 0).")]
        if settings.calculator_mock:
            for name, value in (state.get("vorgaben") or {}).items():
                w = VariablenWert(name=name, wert=Decimal(str(value)), quelle=M.HITL,
                                  beleg=PROVENANCE_CHAT)
                chat_werte[name] = wert_to_json(w)
                log.append(reason("extract_chat_values", REASONING_NARRATION,
                                  f"Aus dem Chat übernommen: {name} = {value}."))
            for name, value in (state.get("globale_vorgaben") or {}).items():
                if name in chat_globals:
                    chat_global[name] = {"wert": str(value), "beleg": PROVENANCE_CHAT, "quelle": "chat"}
        else:
            transcript = state.get("chat_verlauf") or []
            if transcript:
                ergebnis, prov = await llm_calls.extract_chat_values(
                    llm, transcript, chat_katalog_mit_global(),
                    prompt=prompts[PromptType.EKT_CHAT_VALUES],
                    project_uuid=state.get("project_uuid"),
                    conversation_uuid=state.get("conversation_uuid"))
                if prov:
                    log.append(reason("extract_chat_values", REASONING_PROVIDER, prov))
                for z in ergebnis.zuweisungen:
                    if z.name in chat_globals:
                        # True globals (locations are strings) are kept verbatim, not coerced.
                        chat_global[z.name] = {"wert": z.wert, "beleg": z.beleg, "quelle": "chat"}
                        log.append(reason("extract_chat_values", REASONING_NARRATION,
                                          f"Globaler Kandidat aus dem Chat: {z.name} = {z.wert}."))
                        continue
                    val = _coerce_decimal(z.wert)
                    if z.name not in KATALOG or val is None:
                        continue
                    chat_werte[z.name] = wert_to_json(VariablenWert(
                        name=z.name, wert=val, quelle=M.HITL, beleg=z.beleg))
                    log.append(reason("extract_chat_values", REASONING_NARRATION,
                                      f"Aus dem Chat übernommen: {z.name} = {z.wert}."))
        if not chat_werte and not chat_global:
            log.append(reason("extract_chat_values", REASONING_NARRATION,
                              "Keine vorab genannten Werte gefunden."))
        return {"chat_werte": chat_werte, "chat_global_kandidaten": chat_global,
                "reasoning_log": log}

    async def load_project_context(state: PositionKalkulationState) -> dict:
        """Load the project globals (current versions + resolve any missing via RAG) and reconcile
        them against the chat candidates. Delegates the DB/retrieval work to the injected loader;
        with no loader (standalone tests) it uses any pre-seeded `projekt_kontext` and skips RAG."""
        kandidaten = state.get("chat_global_kandidaten") or {}
        if project_context_loader is None:
            kontext = dict(state.get("projekt_kontext") or {})
            return {
                "projekt_kontext": kontext,
                "projekt_kontext_reconcile": _reconcile_global(kontext, kandidaten),
                "reasoning_log": [reason("load_project_context", REASONING_NARRATION,
                                         "Kein Projektkontext-Dienst — verwende vorhandene Werte.")],
            }
        result = await project_context_loader(state["project_uuid"], kandidaten)
        kontext = result.get("projekt_kontext") or {}
        reconcile = result.get("reconcile") or _reconcile_global(kontext, kandidaten)
        gesetzt = [k for k in GLOBAL_VAR_NAMES if kontext.get(k)]
        return {
            "projekt_kontext": kontext,
            "projekt_kontext_reconcile": reconcile,
            "reasoning_log": [reason("load_project_context", REASONING_NARRATION,
                                     f"Projektkontext geladen: {len(gesetzt)} globale Variable(n) gesetzt.")],
        }

    async def project_context_review(state: PositionKalkulationState) -> dict:
        """Pre-Gate-A: let the Kalkulator confirm/override the project globals (Confirm / Override /
        resolve-Conflict per variable), with a map of the geocoded Baustelle to confirm. The submit
        persists changed fields as new versions via the injected saver. A required global that is not
        validly resolved (the Baustelle must geocode to coordinates) blocks the run: the router loops
        back here until it resolves or the Kalkulator cancels. Skipped entirely with no seams."""
        if project_context_loader is None and project_context_saver is None:
            return {"reasoning_log": [reason("project_context_review", REASONING_NARRATION,
                                             "Projektkontext-Prüfung übersprungen.")]}
        kontext = state.get("projekt_kontext") or {}
        reconcile = state.get("projekt_kontext_reconcile") or {}
        payload = {
            "stage": STAGE_PROJECT_CONTEXT_REVIEW,
            "project_uuid": str(state["project_uuid"]),   # lets the gate render the Baustelle map
            "projekt_kontext": kontext,
            "reconcile": reconcile,
        }
        fehlend = fehlende_erforderliche(kontext)
        if fehlend:
            payload["fehlende_erforderliche"] = fehlend
            payload["fehler"] = _erforderlich_fehler(fehlend)
        antwort = interrupt(payload) or {}
        if antwort.get("cancel"):
            return {"abgebrochen": True,
                    "reasoning_log": [reason("project_context_review", REASONING_NARRATION,
                                             "Projektkontext abgebrochen — Kalkulation gestoppt.")]}
        updates = {k: v for k, v in (antwort.get("projekt_kontext") or {}).items() if v not in (None, "")}
        log = []
        if updates and project_context_saver is not None:
            kontext = await project_context_saver(state["project_uuid"], updates)
            log.append(reason("project_context_review", REASONING_NARRATION,
                              f"{len(updates)} globale Variable(n) überschrieben und gespeichert."))
        else:
            log.append(reason("project_context_review", REASONING_NARRATION, "Projektkontext bestätigt."))
        noch_fehlend = fehlende_erforderliche(kontext)
        if noch_fehlend:
            log.append(reason("project_context_review", REASONING_NARRATION,
                              _erforderlich_fehler(noch_fehlend) + " Bitte korrigieren."))
        return {"projekt_kontext": kontext, "reasoning_log": log}

    async def classify_leistung(state: PositionKalkulationState) -> dict:
        """Map the position to a Leistung. Mock honours `position.leistung_hint`; live runs
        the classification prompt over the position + retrieved project context."""
        pos = state["position"]
        log = [reason("classify_leistung", REASONING_NARRATION,
                      "Ordne die Position einer Leistung zu (Langtext ist maßgeblich).")]
        if settings.calculator_mock:
            leistung_key = pos.get(POSITION_LEISTUNG_HINT)
            if leistung_key not in LEISTUNGEN:
                raise ValueError(f"mock classify: unbekannte/fehlende leistung_hint {leistung_key!r}")
        else:
            snippets = await retrieve(f"{pos['kurztext']} {pos.get('langtext') or ''}")
            log.append(reason("classify_leistung", REASONING_NARRATION,
                              f"{len(snippets)} Kontext-Auszug(e) retrievt; klassifiziere."))
            res, prov = await llm_calls.classify_leistung(
                llm, pos, leistung_index(), snippets,
                prompt=prompts[PromptType.EKT_LEISTUNG_CLASSIFY],
                project_uuid=state.get("project_uuid"),
                conversation_uuid=state.get("conversation_uuid"))
            log += reason_llm("classify_leistung", res.reasoning, prov)
            leistung_key = res.leistung_key
            log.append(reason("classify_leistung", REASONING_NARRATION,
                              f"Leistung: {leistung_key} @ {res.konfidenz:.2f}: {res.notizen}"))
        kand = kandidaten(leistung_key) if leistung_key in LEISTUNGEN else []
        name = LEISTUNGEN[leistung_key].name if leistung_key in LEISTUNGEN else leistung_key
        out: dict = {"leistung_key": leistung_key, "leistung_name": name,
                     "bauverfahren_kandidaten": kand, "reasoning_log": log}
        if leistung_key not in LEISTUNGEN:
            out["warnungen"] = [f"Leistung '{leistung_key}' nicht im Katalog — in Gate 2 korrigieren."]
        return out

    def leistung_bv_review(state: PositionKalkulationState) -> dict:
        """Gate 2: confirm (or correct) the Leistung and select the Bauverfahren. Machines and
        material are decided at later gates (they depend on the confirmed recipe). The full Leistung
        catalog is offered so an unclassified position can still be assigned; cancel aborts."""
        lk = state["leistung_key"]
        kand = state["bauverfahren_kandidaten"]
        antwort = interrupt({
            "stage": STAGE_LEISTUNG_BV_REVIEW,
            "leistung_key": lk,
            "leistung_name": state.get("leistung_name"),
            "bauverfahren_kandidaten": kand,
            "bauverfahren_default": kand[0] if kand else None,
            "katalog": leistung_katalog(),
            "bauverfahren_ressourcen": bauverfahren_ressourcen(),
        }) or {}
        if antwort.get("cancel"):
            return {"abgebrochen": True,
                    "reasoning_log": [reason("leistung_bv_review", REASONING_NARRATION,
                                             "Kalkulation vom Kalkulator abgebrochen.")]}
        confirmed_lk = antwort.get("leistung_key") or lk
        if confirmed_lk not in LEISTUNGEN:
            raise ValueError(f"unbekannte Leistung in Gate 2: {confirmed_lk!r}")
        bv = waehle_bauverfahren(confirmed_lk, antwort.get("bauverfahren_key"))
        out = {
            "leistung_key": confirmed_lk,
            "bauverfahren_key": bv,
            "reasoning_log": [reason("leistung_bv_review", REASONING_NARRATION,
                                     f"Leistung {confirmed_lk} bestätigt; Bauverfahren {bv} gewählt.")],
        }
        if confirmed_lk != lk:
            out["leistung_name"] = LEISTUNGEN[confirmed_lk].name
            out["bauverfahren_kandidaten"] = kandidaten(confirmed_lk)
        return out

    def resolve_material(state: PositionKalkulationState) -> dict:
        """After the recipe is confirmed: BM25-propose the acquisition Baustoff it consumes. Returns
        no proposal when the recipe needs no material (e.g. Fräsen) — the router then skips Gate 3."""
        vorschlag = _baustoff_match([state["bauverfahren_key"]], state["position"])
        if vorschlag is None:
            return {"reasoning_log": [reason("resolve_material", REASONING_NARRATION,
                                             "Rezept benötigt kein Material — kein Material-Gate.")]}
        log = [reason("resolve_material", REASONING_NARRATION,
                      "Ermittle das Material für das gewählte Rezept.")]
        if vorschlag["code"]:
            log.append(reason("resolve_material", REASONING_NARRATION,
                              f"Baustoff erkannt (BM25): {vorschlag['name']} — Konfidenz "
                              f"{vorschlag['konfidenz']:.2f}, zur Prüfung in Gate 3."))
        else:
            log.append(reason("resolve_material", REASONING_NARRATION,
                              "Rezept benötigt Baustoff, kein eindeutiger Treffer — Auswahl in Gate 3."))
        return {"baustoff_vorschlag": vorschlag, "reasoning_log": log}

    def material_review(state: PositionKalkulationState) -> dict:
        """Gate 3: confirm (or correct) the acquisition Baustoff for the confirmed recipe. Reached
        only when the recipe needs a material; the supplier is ranked next, against this choice, so a
        correction here re-ranks (no stale supplier list). Cancel aborts."""
        vorschlag = state.get("baustoff_vorschlag") or {}
        auto = vorschlag.get("code") if vorschlag.get("auto") else None
        antwort = interrupt({
            "stage": STAGE_MATERIAL_REVIEW,
            "baustoff_vorschlag": vorschlag,
            "baustoff_katalog": baustoff_katalog(),
        }) or {}
        if antwort.get("cancel"):
            return {"abgebrochen": True,
                    "reasoning_log": [reason("material_review", REASONING_NARRATION,
                                             "Kalkulation vom Kalkulator abgebrochen.")]}
        bc = antwort.get("baustoff_code") or auto or state["position"].get("baustoff_code")
        return {"baustoff_code": bc,
                "reasoning_log": [reason("material_review", REASONING_NARRATION,
                                         f"Material bestätigt: {bc}." if bc else "Kein Material bestätigt.")]}

    async def rank_lieferanten(state: PositionKalkulationState) -> dict:
        """Rank suppliers for the CONFIRMED Baustoff (Gate 3) using the confirmed project Baustelle
        coords, so Gate 4 can offer a supplier picker. A material-free position needs no supplier;
        without confirmed coords the ranking is deferred (catalog price applies)."""
        bc = state.get("baustoff_code")
        if not bc:
            return {"reasoning_log": [reason("rank_lieferanten", REASONING_NARRATION,
                    "Kein Material in der Position — Lieferantenwahl entfällt.")]}
        kontext = state.get("projekt_kontext") or {}
        lat_s, lon_s = kontext.get("baustelle_breitengrad"), kontext.get("baustelle_laengengrad")
        if not lat_s or not lon_s:
            return {"reasoning_log": [reason("rank_lieferanten", REASONING_NARRATION,
                    "Kein bestätigter Baustellenstandort — Lieferantenwahl per Katalogpreis/Default.")]}
        lat, lon = Decimal(str(lat_s)), Decimal(str(lon_s))
        log = [reason("rank_lieferanten", REASONING_NARRATION,
                      f"Ranke Lieferanten für {bc} ab Baustelle ({lat}, {lon}).")]
        rangliste = await rang_lieferanten(bc, lat, lon)
        out: dict = {}
        if rangliste.warnung:
            log.append(reason("rank_lieferanten", REASONING_NARRATION, rangliste.warnung))
            out["warnungen"] = [rangliste.warnung]
        if rangliste.angebote:
            out["lieferanten_vorschlag"] = {bc: {
                "default": rangliste.angebote[0].code,
                "angebote": [a.model_dump(mode="json") for a in rangliste.angebote]}}
            out["gewaehlter_lieferant"] = {bc: rangliste.angebote[0].code}   # cheapest, overridable at Gate 4
            log.append(reason("rank_lieferanten", REASONING_NARRATION,
                              f"{len(rangliste.angebote)} Lieferant(en) für {bc} gerankt; günstigster: "
                              f"{rangliste.angebote[0].name} "
                              f"({rangliste.angebote[0].frei_bau_eur_pro_t} €/t frei Baustelle)."))
        out["reasoning_log"] = log
        return out

    def bind_resources(state: PositionKalkulationState) -> dict:
        """After the recipe is chosen: attempt to select a machine per Ausführungsart slot
        (honouring a Gate A pick, else the default candidate) and read its rates + productivity
        into `maschinen_werte`. An unbound slot falls to the org-default / Gate B. Material is
        carried as `baustoff_code` and attached at compute."""
        bv = BAUVERFAHREN[state["bauverfahren_key"]]
        picks = state.get("gewaehlte_maschinen") or {}
        menge = Decimal(str(state["position"]["menge"]))
        ziel = Decimal(str(settings.calculator_maschine_zielstunden))
        bedarf = (menge / ziel) if ziel > 0 else None
        # TODO: New Feature — each Vorgang currently binds exactly one Ausführungsart (fixed in
        # vorgaenge.py), so no selection happens here. Once a Vorgang admits multiple
        # Ausführungsarten, the correct (or more correct) one must be chosen per position,
        # probably via a dedicated prompt — and that choice needs its own eval.
        slots = list(dict.fromkeys(vg.ausfuehrungsart.code for vg in bv.vorgaenge
                                   if vg.ausfuehrungsart is not None))
        auswahl: dict = {}
        gewaehlt: dict = {}
        kandidaten_je_slot: dict = {}
        log = [reason("bind_resources", REASONING_NARRATION,
                      f"Wähle Maschinen für {len(slots)} Geräteplatz/-plätze des Rezepts {bv.code}.")]
        for slot in slots:
            # Right-sized order; kand[0] is the smallest machine that clears the job in time.
            kand = maschinen_sortiert(slot, betriebsart_code=_slot_betriebsart(bv, slot),
                                      bedarf_pro_stunde=bedarf)
            kandidaten_je_slot[slot] = [{"code": m.code, "hersteller": m.hersteller, "modell": m.modell}
                                        for m in kand]
            code = picks.get(slot) or (kand[0].code if kand else None)
            if code and code in MASCHINEN:
                auswahl[slot] = MASCHINEN[code]
                gewaehlt[slot] = code
                log.append(reason("bind_resources", REASONING_NARRATION,
                                  f"{slot}: {MASCHINEN[code].hersteller} {MASCHINEN[code].modell}."))
            else:
                log.append(reason("bind_resources", REASONING_NARRATION,
                                  f"{slot}: keine Maschine im Katalog → Sätze zur Prüfung (Gate B)."))
        werte = {n: wert_to_json(w) for n, w in rezept_maschinen_werte(bv, auswahl).items()}
        if state.get("baustoff_code"):
            log.append(reason("bind_resources", REASONING_NARRATION,
                              f"Baustoff: {state['baustoff_code']}."))
        return {"gewaehlte_maschinen": gewaehlt, "maschinen_kandidaten": kandidaten_je_slot,
                "maschinen_werte": werte, "reasoning_log": log}

    def bind_lieferant(state: PositionKalkulationState) -> dict:
        """Finalize the supplier for the bound Baustoff: honour the Gate A pick iff that supplier
        carries the final material, else auto-pick cheapest-delivered (mirror of the machine-pick
        fallback). Reuses the ranking already computed at rank_lieferanten from the confirmed
        project Baustelle coords (no re-geocode). Stashes the ex-works price override + the supplier
        road distance for compute/Gate B."""
        bc = state.get("baustoff_code")
        log = [reason("bind_lieferant", REASONING_NARRATION, "Lieferant für das Material festlegen.")]
        if not bc:
            log.append(reason("bind_lieferant", REASONING_NARRATION,
                              "Kein Material — Materialpreis aus Katalog."))
            return {"reasoning_log": log}

        out: dict = {}
        vorschlag = (state.get("lieferanten_vorschlag") or {}).get(bc) or {}
        angebote = [LieferantAngebot.model_validate(a) for a in vorschlag.get("angebote", [])]
        if not angebote:
            log.append(reason("bind_lieferant", REASONING_NARRATION,
                              f"Kein Lieferant für {bc} (kein Standort/Treffer) — Katalogpreis, "
                              "Default-Antransport."))
            out["reasoning_log"] = log
            return out
        by_code = {a.code: a for a in angebote}
        pick = (state.get("gewaehlter_lieferant") or {}).get(bc)
        chosen = by_code.get(pick) or angebote[0]
        preis_beleg = (f"Lieferant {chosen.name} ({chosen.ort}), Werkspreis "
                       f"{chosen.werk_eur_pro_t} €/t frei Werk, Stichtag {STICHTAG}")
        dist_beleg = f"{chosen.name} ({chosen.ort}) → Baustelle, {chosen.strasse_km} km (Google Routes)"
        dist = VariablenWert(name=LIEFERANT_DISTANCE_VAR, wert=chosen.strasse_km,
                             quelle=M.STAMMDATEN, beleg=dist_beleg)
        log.append(reason("bind_lieferant", REASONING_NARRATION,
                          f"Lieferant {chosen.name}: Werk {chosen.werk_eur_pro_t} €/t + "
                          f"{chosen.strasse_km} km → {chosen.frei_bau_eur_pro_t} €/t frei Baustelle; "
                          f"günstigster von {len(angebote)}."))
        out.update({
            "lieferant_code": chosen.code,
            "lieferant_werkspreis": str(chosen.werk_eur_pro_t),
            "lieferant_beleg": preis_beleg,
            "lieferant_werte": {LIEFERANT_DISTANCE_VAR: wert_to_json(dist)},
            "reasoning_log": log,
        })
        return out

    def derive_required_variables(state: PositionKalkulationState) -> dict:
        """Walk the chosen recipe's formula tree to all leaves -> the Gate B worklist.
        The geometry variable booked from the LV Menge is pruned (already resolved)."""
        bv = BAUVERFAHREN[state["bauverfahren_key"]]
        einheit = LEISTUNGEN[state["leistung_key"]].einheit
        geom = GEOM[einheit]
        blaetter = benoetigte_variablen(bv, kalk, gebucht=frozenset({geom}))
        return {
            "benoetigte": [b.model_dump(mode="json") for b in blaetter],
            "reasoning_log": [reason("derive_required_variables", REASONING_NARRATION,
                                     f"Rezept {bv.code}: {len(blaetter)} Variablen aufzulösen "
                                     f"(Geometrie {geom} aus der Menge gebucht).")],
        }

    async def resolve_variables(state: PositionKalkulationState) -> dict:
        """Propose a value + provenance + review tier for every worklist leaf. Chat-pinned
        leaves win; extracted inputs run the cascade (mock: default fallback only); rates and
        Stammdaten are catalog lookups shown for transparency."""
        schwelle = state["konfidenz_schwelle_review"]
        chat_werte = state.get("chat_werte") or {}
        # Values bound before Gate B: project globals (deponie distance, fräsgut default, strip
        # geometry fallback), machine rates/productivity, and the supplier haul distance. They each
        # become a Gate B proposal (collapsed, overridable) for their leaf. Precedence §3: a
        # per-position resource pick outranks a project global, so the project values merge first.
        projekt_werte = _projekt_werte(state.get("projekt_kontext") or {})
        gebundene_werte = {**projekt_werte, **(state.get("maschinen_werte") or {}),
                           **(state.get("lieferant_werte") or {})}
        position = state["position"]
        # The chosen Baustoff with the supplier ex-works price applied, so STAMMDATEN price bridges
        # show the supplier price at Gate B (not the catalog base).
        baustoff = _effektiver_baustoff(state.get("baustoff_code"), state.get("lieferant_werkspreis"))
        vorschlaege: dict = {}
        log = [reason("resolve_variables", REASONING_NARRATION,
                      f"Löse {len(state['benoetigte'])} Variablen auf (Schwelle {schwelle}).")]

        for b in state["benoetigte"]:
            name, art, hochrisiko = b["name"], b["art"], b["hochrisiko"]
            if name not in chat_werte and name in gebundene_werte:
                wj = gebundene_werte[name]   # project global, machine rate/productivity, or supplier distance
                defn = KATALOG[name]
                # A high-stakes leaf (e.g. fraesgut_klasse) stays surfaced even when the project
                # default pre-fills it; rates/distances (not hochrisiko) stay collapsed.
                v = VariablenVorschlag(name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit,
                                       art=art, hochrisiko=hochrisiko,
                                       tier=TIER_SURFACED if hochrisiko else TIER_COLLAPSED,
                                       wert=wj["wert"], quelle=wj["quelle"], beleg=wj["beleg"])
            else:
                v = _catalog_vorschlag(name, art, hochrisiko, chat_werte, baustoff)
                if v is None:                             # unpinned EINGABE leaf
                    if settings.calculator_mock:
                        default = _konstante_wert(KATALOG[name])
                        v = (_eingabe_vorschlag(name, KATALOG[name], hochrisiko, schwelle, default,
                                                M.KONSTANTE, None, PROVENANCE_DEFAULT)
                             if default is not None
                             else _unresolved_vorschlag(name, KATALOG[name], hochrisiko))
                    else:
                        v, vlog = await _resolve_eingabe(name, hochrisiko, schwelle, position, state)
                        log += vlog
            vorschlaege[name] = v.model_dump(mode="json")

        surfaced = sum(1 for v in vorschlaege.values() if v["tier"] == TIER_SURFACED)
        log.append(reason("resolve_variables", REASONING_NARRATION,
                          f"{surfaced} Variable(n) zur Prüfung vorgelegt, Rest vorab akzeptiert."))
        return {"vorschlaege": vorschlaege, "reasoning_log": log}

    def variable_review(state: PositionKalkulationState) -> dict:
        """Gate 4: machines + supplier + every worklist leaf (surfaced for decision, collapsed
        pre-accepted). Changing the machine model re-binds its rates; changing the supplier re-applies
        that ranked offer's ex-works price + road distance. The submit writes the confirmed `werte`."""
        vorschlaege = state["vorschlaege"]
        surfaced = [v for v in vorschlaege.values() if v["tier"] == TIER_SURFACED]
        collapsed = [v for v in vorschlaege.values() if v["tier"] == TIER_COLLAPSED]
        antwort = interrupt({
            "stage": STAGE_VARIABLE_REVIEW,
            "konfidenz_schwelle_review": state["konfidenz_schwelle_review"],
            "surfaced": surfaced,
            "collapsed": collapsed,
            "maschinen_kandidaten": state.get("maschinen_kandidaten") or {},
            "gewaehlte_maschinen": state.get("gewaehlte_maschinen") or {},
            "lieferanten_vorschlag": state.get("lieferanten_vorschlag") or {},
            "gewaehlter_lieferant": state.get("gewaehlter_lieferant") or {},
        }) or {}

        out: dict = {}
        log: list[dict] = []
        maschinen_werte = state.get("maschinen_werte") or {}
        lieferant_werte = state.get("lieferant_werte") or {}

        # Machine model changed -> re-bind that slot's rates/productivity. They feed compute via
        # maschinen_werte, so they need no entry in `werte` (see the `gebunden` skip below).
        maschinen_pick = antwort.get("maschinen") or {}
        if maschinen_pick and maschinen_pick != (state.get("gewaehlte_maschinen") or {}):
            bv = BAUVERFAHREN[state["bauverfahren_key"]]
            auswahl = {slot: MASCHINEN[c] for slot, c in maschinen_pick.items() if c in MASCHINEN}
            maschinen_werte = {n: wert_to_json(w) for n, w in rezept_maschinen_werte(bv, auswahl).items()}
            out["maschinen_werte"] = maschinen_werte
            out["gewaehlte_maschinen"] = maschinen_pick
            log.append(reason("variable_review", REASONING_NARRATION, "Maschinenauswahl aktualisiert."))

        # Supplier changed -> re-apply the chosen offer's ex-works price + road distance from the
        # already-ranked list (no re-routing). compute rebuilds the price bridge from the werkspreis.
        bc = state.get("baustoff_code")
        pick = (antwort.get("lieferanten") or {}).get(bc) if bc else None
        if bc and pick and pick != (state.get("gewaehlter_lieferant") or {}).get(bc):
            angebote = {a["code"]: a for a in
                        ((state.get("lieferanten_vorschlag") or {}).get(bc) or {}).get("angebote", [])}
            raw = angebote.get(pick)
            if raw is not None:
                chosen = LieferantAngebot.model_validate(raw)
                dist = VariablenWert(name=LIEFERANT_DISTANCE_VAR, wert=chosen.strasse_km, quelle=M.STAMMDATEN,
                                     beleg=f"{chosen.name} ({chosen.ort}) → Baustelle, "
                                           f"{chosen.strasse_km} km (Google Routes)")
                lieferant_werte = {LIEFERANT_DISTANCE_VAR: wert_to_json(dist)}
                out.update({
                    "lieferant_code": chosen.code,
                    "lieferant_werkspreis": str(chosen.werk_eur_pro_t),
                    "lieferant_beleg": (f"Lieferant {chosen.name} ({chosen.ort}), Werkspreis "
                                        f"{chosen.werk_eur_pro_t} €/t frei Werk, Stichtag {STICHTAG}"),
                    "lieferant_werte": lieferant_werte,
                    "gewaehlter_lieferant": {**(state.get("gewaehlter_lieferant") or {}), bc: chosen.code},
                })
                log.append(reason("variable_review", REASONING_NARRATION,
                                  f"Lieferant geändert: {chosen.name} ({chosen.werk_eur_pro_t} €/t, "
                                  f"{chosen.strasse_km} km)."))

        # Bound values (machine rates, supplier distance) reach compute via their own dicts; only
        # UNBOUND EINGABE proposals are written into `werte` (an explicit override always wins).
        gebunden = set(maschinen_werte) | set(lieferant_werte)
        overrides = antwort.get("overrides") or {}
        werte: dict = {}
        updated = dict(vorschlaege)
        warnungen: list[str] = []
        ueberschrieben = 0
        for name, v in vorschlaege.items():
            defn = KATALOG[name]
            if name in overrides:
                val = _parse_override(overrides[name])
                if val is not None:
                    ueberschrieben += 1
                    werte[name] = wert_to_json(VariablenWert(name=name, wert=val, quelle=M.HITL,
                                                             beleg=PROVENANCE_OVERRIDE))
                    updated[name] = {**v, "wert": str(val), "quelle": M.HITL.value,
                                     "status": STATUS_UEBERSCHRIEBEN}
                    continue
                warnungen.append(f"{name} ({defn.bezeichnung}): »{overrides[name]}« ist keine "
                                 f"gültige Zahl — Überschreibung verworfen, Vorschlag übernommen.")
            updated[name] = {**v, "status": STATUS_AKZEPTIERT}
            # Engine resolves SATZ/STAMMDATEN itself; only unbound EINGABE values must be pre-filled.
            if v["art"] == BlattArt.EINGABE.value and name not in gebunden:
                if v["wert"] is None:
                    warnungen.append(f"{name} ({defn.bezeichnung}) ohne Wert bestätigt — "
                                     f"Kalkulation kann scheitern.")
                else:
                    werte[name] = wert_to_json(VariablenWert(
                        name=name, wert=Decimal(v["wert"]),
                        quelle=M(v["quelle"]) if v["quelle"] else M.HITL,
                        konfidenz=Decimal(v["konfidenz"]) if v["konfidenz"] else None,
                        beleg=v["beleg"]))
        out.update({
            "werte": werte,
            "vorschlaege": updated,
            "warnungen": warnungen,
            "reasoning_log": log + [reason("variable_review", REASONING_NARRATION,
                                           f"{ueberschrieben} Wert(e) überschrieben, übrige akzeptiert.")],
        })
        return out

    def compute(state: PositionKalkulationState) -> dict:
        """Deterministic: build the context from the confirmed werte + booked geometry,
        run the recipe, emit the EKT row and the Nachweistabelle from `ctx.werte`."""
        pos = state["position"]
        leistung_key = state["leistung_key"]
        bv_key = state["bauverfahren_key"]
        einheit = LEISTUNGEN[leistung_key].einheit
        menge = Decimal(str(pos["menge"]))
        geom = GEOM[einheit]

        bc = state.get("baustoff_code")
        baustoff = _effektiver_baustoff(bc, state.get("lieferant_werkspreis"))  # supplier price override
        stammdaten = {"baustoff": baustoff} if baustoff is not None else {}
        ctx = Kalkulationskontext(stichtag=STICHTAG, stammdaten=stammdaten)
        ctx.werte[geom] = VariablenWert(name=geom, wert=menge, quelle=M.LANGTEXT,
                                        beleg=f"LV Menge {menge} {einheit}")
        for name, wj in (state.get("maschinen_werte") or {}).items():   # machine rates + productivity
            ctx.werte[name] = wert_from_json(wj)
        for name, wj in (state.get("lieferant_werte") or {}).items():   # supplier distance (Gate B may override)
            ctx.werte[name] = wert_from_json(wj)
        for name, wj in (state.get("werte") or {}).items():             # Gate B confirmed (overrides win)
            ctx.werte[name] = wert_from_json(wj)

        try:
            ergebnis = kalkuliere_kontext(leistung_key, bv_key, ctx, menge)
        except Exception as exc:
            return {"warnungen": [f"Kalkulation fehlgeschlagen: {' '.join(str(exc).split())}"],
                    "reasoning_log": [reason("compute", REASONING_NARRATION,
                                             "Kalkulation fehlgeschlagen (siehe Warnungen).")]}

        ekt_zeile = EKTZeile(
            oz=pos["oz"], leistung_key=leistung_key, leistung=ergebnis["leistung"],
            bauverfahren=bv_key, einheit=ergebnis["einheit"], menge=menge,
            ep_eur=ergebnis["ep_eur"], gp_eur=ergebnis["ekt_eur"],
            kostenlinien=[KostenLinie(vorgang=vg["vorgang"], kostenart=p["kostenart"],
                                      variable=p["variable"], betrag_eur=p["betrag_eur"],
                                      quelle=p["quelle"])
                          for vg in ergebnis["detail"] for p in vg["positionen"]],
        )
        return {
            "ekt_zeile": ekt_zeile.model_dump(mode="json"),
            "nachweis_tabelle": [n.model_dump(mode="json")
                                 for n in _nachweis(ctx, state.get("lieferant_beleg"))],
            "reasoning_log": [reason("compute", REASONING_NARRATION,
                                     f"EKT berechnet: EP {ergebnis['ep_eur']} €/{ergebnis['einheit']}, "
                                     f"GP {ergebnis['ekt_eur']} €.")],
        }

    async def render_output(state: PositionKalkulationState) -> dict:
        """Narrate the result. Mock writes a deterministic summary; live runs the narration
        prompt over the EKT row + Nachweistabelle."""
        ekt = state.get("ekt_zeile")
        if ekt is None:
            return {"beschreibung": None}
        if settings.calculator_mock:
            beschreibung = (
                f"Position {ekt['oz']} ({ekt['leistung']}) über Bauverfahren {ekt['bauverfahren']}: "
                f"EP {ekt['ep_eur']} €/{ekt['einheit']}, GP {ekt['gp_eur']} €.")
        else:
            beschreibung = await llm_calls.narrate_output(
                llm, ekt, state.get("nachweis_tabelle", []),
                prompt=prompts[PromptType.EKT_OUTPUT_NARRATE],
                project_uuid=state.get("project_uuid"),
                conversation_uuid=state.get("conversation_uuid"))
        return {
            "beschreibung": beschreibung,
            "reasoning_log": [reason("render_output", REASONING_NARRATION,
                                     "Ergebnis und Nachweistabelle erstellt.")],
        }

    g = StateGraph(PositionKalkulationState)
    g.add_node("launch", launch)
    g.add_node("extract_chat_values", extract_chat_values)
    g.add_node("load_project_context", load_project_context)
    g.add_node("project_context_review", project_context_review)
    g.add_node("classify_leistung", classify_leistung)
    g.add_node("leistung_bv_review", leistung_bv_review)
    g.add_node("resolve_material", resolve_material)
    g.add_node("material_review", material_review)
    g.add_node("rank_lieferanten", rank_lieferanten)
    g.add_node("bind_resources", bind_resources)
    g.add_node("bind_lieferant", bind_lieferant)
    g.add_node("derive_required_variables", derive_required_variables)
    g.add_node("resolve_variables", resolve_variables)
    g.add_node("variable_review", variable_review)
    g.add_node("compute", compute)
    g.add_node("render_output", render_output)

    def _route_after_project_context(state: PositionKalkulationState) -> str:
        """Block the run at the review gate until every required global is validly resolved: an
        unresolved required global loops back to the gate; a cancel aborts. With no seams (standalone
        tests) enforcement is off — the gate cannot resolve anything, so proceeding is the only option."""
        if state.get("abgebrochen"):
            return END
        if project_context_loader is None and project_context_saver is None:
            return "classify_leistung"
        if fehlende_erforderliche(state.get("projekt_kontext") or {}):
            return "project_context_review"
        return "classify_leistung"

    g.add_edge(START, "launch")
    g.add_edge("launch", "extract_chat_values")
    g.add_edge("extract_chat_values", "load_project_context")
    g.add_edge("load_project_context", "project_context_review")
    g.add_conditional_edges("project_context_review", _route_after_project_context,
                            ["classify_leistung", "project_context_review", END])
    g.add_edge("classify_leistung", "leistung_bv_review")
    g.add_conditional_edges("leistung_bv_review", _route_after_leistung_bv,
                            ["resolve_material", END])
    g.add_conditional_edges("resolve_material", _route_after_resolve_material,
                            ["material_review", "rank_lieferanten"])
    g.add_conditional_edges("material_review", _route_after_material,
                            ["rank_lieferanten", END])
    g.add_edge("rank_lieferanten", "bind_resources")
    g.add_edge("bind_resources", "bind_lieferant")
    g.add_edge("bind_lieferant", "derive_required_variables")
    g.add_edge("derive_required_variables", "resolve_variables")
    g.add_edge("resolve_variables", "variable_review")
    g.add_edge("variable_review", "compute")
    g.add_edge("compute", "render_output")
    g.add_edge("render_output", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
