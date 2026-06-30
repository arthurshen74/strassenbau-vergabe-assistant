# pyright: reportTypedDictNotRequiredAccess=false
"""LangGraph wiring for the EKT position-calculation agent (kalkulation_v2 engine).

Topology (ARCHITECTURE §7), per position:
  launch -> extract_chat_values -> classify_leistung
  -> locate_baustelle (geocode the site + rank suppliers for the proposed material)
  -> method_review (Gate A interrupt: confirm Leistung, select Bauverfahren + resources + supplier)
  -> bind_resources (auto-select a machine per slot + baustoff)
  -> bind_lieferant (finalize the supplier -> ex-works price override + Antransport distance)
  -> derive_required_variables -> resolve_variables
  -> variable_review (Gate B interrupt: accept/override every leaf, tiered)
  -> compute (deterministic kalkuliere) -> render_output

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

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from shared.clients.llm.client import LLMClient
from shared.clients.maps.geo import MapsError, geocode
from shared.config import settings
from shared.models.enums import PromptType, RetrievalModality
from shared.models.prompt_version import PromptVersion
from shared.services.calculator import llm_calls
from shared.services.calculator.lieferant_ranking import rang_lieferanten
from shared.services.calculator.state import (
    BAUSTELLE_FEHLT,
    BAUSTELLE_OK,
    BAUSTELLE_UNSICHER,
    DEFAULT_REVIEW_SCHWELLE,
    STAGE_METHOD_REVIEW,
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
# A geocoded Baustelle below this confidence is flagged for HITL confirmation at Gate A (§9).
GEOCODE_HITL_THRESHOLD = 0.6
# STAMMDATEN beleg prefix every material price bridge shares (all read baustoff.basispreis*).
STAMMDATEN_PREIS_PRAEFIX = "baustoff.basispreis"

# Leistung label space + chat-extraction catalog, built once from the engine.
LEISTUNG_INDEX = [{"leistung_key": k, "name": v.name, "standard_kennung": v.standard_kennung}
                  for k, v in LEISTUNGEN.items()]
CHAT_KATALOG = [{"name": n, "bezeichnung": d.bezeichnung, "einheit": d.einheit}
                for n, d in KONTEXT_VARIABLEN.items()]
# Full Leistung -> candidate Bauverfahren map for the Gate A method-review UI, so the Kalkulator can
# correct the classification and pick a recipe even when the position did not classify cleanly.
LEISTUNG_KATALOG = [{"leistung_key": k, "name": v.name, "kandidaten": kandidaten(k)}
                    for k, v in LEISTUNGEN.items()]

# Per-Bauverfahren machine slots + candidates, so Gate A can offer a machine picker per slot once a
# recipe is chosen. Only slots with >=1 catalog machine are pickable. Baustoff catalog for the
# material picker (offered optionally; most positions need none).
_AA_BY_CODE = {a.code: a for a in AUSFUEHRUNGSARTEN.values()}


def _bv_slots(bauverfahren) -> list[str]:
    return list(dict.fromkeys(vg.ausfuehrungsart.code for vg in bauverfahren.vorgaenge
                              if vg.ausfuehrungsart is not None and maschinen_fuer(vg.ausfuehrungsart.code)))


BAUVERFAHREN_RESSOURCEN = {
    bv_code: [
        {"slot": slot, "geraet": _AA_BY_CODE[slot].name,
         "kandidaten": [{"code": m.code, "hersteller": m.hersteller, "modell": m.modell}
                        for m in maschinen_fuer(slot)]}
        for slot in _bv_slots(bv)
    ]
    for bv_code, bv in BAUVERFAHREN.items()
}
BAUSTOFF_KATALOG = [{"code": b.code, "name": b.name, "kategorie": b.kategorie}
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


def _maschinen_defaults(bv_key: str, menge: Decimal) -> dict[str, str]:
    """Right-sized default machine per slot for this recipe + job size: the smallest machine
    whose capacity clears the job within the target deployment window
    (settings.calculator_maschine_zielstunden). Calibrated for the recipe's primary machine
    (whose productivity matches the booked geometry); secondary slots are approximate but still
    scale with job size. Falls back to fleet order when the target is unset."""
    bv = BAUVERFAHREN[bv_key]
    ziel = Decimal(str(settings.calculator_maschine_zielstunden))
    bedarf = (menge / ziel) if ziel > 0 else None
    out: dict[str, str] = {}
    for slot in dict.fromkeys(vg.ausfuehrungsart.code for vg in bv.vorgaenge
                              if vg.ausfuehrungsart is not None):
        sortiert = maschinen_sortiert(slot, betriebsart_code=_slot_betriebsart(bv, slot),
                                      bedarf_pro_stunde=bedarf)
        if sortiert:
            out[slot] = sortiert[0].code
    return out


def _route_after_method(state: PositionKalkulationState) -> str:
    return END if state.get("abgebrochen") else "bind_resources"


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


# ------------------------------------------------------------------- build --
def build_graph(
    retriever: ContextRetriever | None,
    llm: LLMClient | None = None,
    prompts: Mapping[PromptType, PromptVersion] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the position-calculation graph. The LLM/RAG nodes close over `retriever`,
    `llm` and `prompts`; all three are unused in mock mode (`settings.calculator_mock`),
    so they may be None there. `checkpointer` persists state across the HITL interrupts
    (defaults to an in-process MemorySaver; the conversation service injects Postgres)."""
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
        """Source 0: harvest values the Kalkulator already stated pre-launch and lock them.
        Mock reads `vorgaben`; live runs the chat-extraction prompt over `chat_verlauf`."""
        chat_werte: dict = {}
        log = [reason("extract_chat_values", REASONING_NARRATION,
                      "Prüfe den Chatverlauf auf bereits genannte Werte (Quelle 0).")]
        if settings.calculator_mock:
            for name, value in (state.get("vorgaben") or {}).items():
                w = VariablenWert(name=name, wert=Decimal(str(value)), quelle=M.HITL,
                                  beleg=PROVENANCE_CHAT)
                chat_werte[name] = wert_to_json(w)
                log.append(reason("extract_chat_values", REASONING_NARRATION,
                                  f"Aus dem Chat übernommen: {name} = {value}."))
        else:
            transcript = state.get("chat_verlauf") or []
            if transcript:
                ergebnis, prov = await llm_calls.extract_chat_values(
                    llm, transcript, CHAT_KATALOG, prompt=prompts[PromptType.EKT_CHAT_VALUES],
                    project_uuid=state.get("project_uuid"),
                    conversation_uuid=state.get("conversation_uuid"))
                if prov:
                    log.append(reason("extract_chat_values", REASONING_PROVIDER, prov))
                for z in ergebnis.zuweisungen:
                    val = _coerce_decimal(z.wert)
                    if z.name not in KATALOG or val is None:
                        continue
                    chat_werte[z.name] = wert_to_json(VariablenWert(
                        name=z.name, wert=val, quelle=M.HITL, beleg=z.beleg))
                    log.append(reason("extract_chat_values", REASONING_NARRATION,
                                      f"Aus dem Chat übernommen: {z.name} = {z.wert}."))
        if not chat_werte:
            log.append(reason("extract_chat_values", REASONING_NARRATION,
                              "Keine vorab genannten Werte gefunden."))
        return {"chat_werte": chat_werte, "reasoning_log": log}

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
                llm, pos, LEISTUNG_INDEX, snippets,
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
            out["warnungen"] = [f"Leistung '{leistung_key}' nicht im Katalog — in Gate A korrigieren."]
        if kand:                                   # right-sized machine default per slot (Gate A pre-fill)
            out["maschinen_default"] = _maschinen_defaults(kand[0], Decimal(str(pos["menge"])))
        vorschlag = _baustoff_match(kand, pos)
        if vorschlag is not None:
            out["baustoff_vorschlag"] = vorschlag
            if vorschlag["code"]:
                log.append(reason("classify_leistung", REASONING_NARRATION,
                                  f"Baustoff erkannt (BM25): {vorschlag['name']} — Konfidenz "
                                  f"{vorschlag['konfidenz']:.2f}, "
                                  f"{'automatisch' if vorschlag['auto'] else 'zur Prüfung in Gate A'}."))
            else:
                log.append(reason("classify_leistung", REASONING_NARRATION,
                                  "Rezept benötigt Baustoff, kein eindeutiger Treffer — Auswahl in Gate A."))
        return out

    async def locate_baustelle(state: PositionKalkulationState) -> dict:
        """Geocode the Baustelle from the Baubeschreibung (mock: a fixture coordinate), then rank
        suppliers for the proposed Baustoff so Gate A can offer a per-material picker. Runs before
        Gate A because supplier ranking needs the site coordinates. A position with no material
        needs no supplier, so geocoding is skipped (the location is per-position for now, §9)."""
        pos = state["position"]
        vorschlag = state.get("baustoff_vorschlag") or {}
        bc = vorschlag.get("code") or pos.get("baustoff_code")
        if not bc:
            return {"reasoning_log": [reason("locate_baustelle", REASONING_NARRATION,
                    "Kein Material in der Position — Standortbestimmung und Lieferantenwahl entfallen.")]}
        log = [reason("locate_baustelle", REASONING_NARRATION,
                      "Bestimme den Standort der Baustelle (Geokodierung der Baubeschreibung).")]
        if settings.calculator_mock:
            res = await geocode(pos.get("langtext") or pos.get("kurztext") or "Baustelle")
        else:
            snippets = await retrieve(
                "Wo liegt die Baustelle? Ort, Gemeinde, Landkreis und Straße bzw. Straßennummer "
                f"des zu sanierenden Abschnitts. {pos.get('kurztext', '')}")
            adresse = (snippets[0][:300].strip() if snippets else "") or \
                pos.get("langtext") or pos.get("kurztext") or ""
            try:
                res = await geocode(adresse)
            except MapsError as exc:
                # Auto-geocode failed — surface the attempt in Gate A so the estimator can enter the
                # location manually (bind_lieferant re-geocodes it). The supplier feature still works.
                log.append(reason("locate_baustelle", REASONING_NARRATION,
                                  f"Geokodierung fehlgeschlagen ({exc}); Standort in Gate A eingeben."))
                return {"baustelle_adresse": adresse[:200] or None,
                        "baustelle_status": BAUSTELLE_FEHLT,
                        "warnungen": ["Baustellenstandort nicht automatisch bestimmt — in Gate A eingeben."],
                        "reasoning_log": log}
        unsicher = not settings.calculator_mock and res.konfidenz < GEOCODE_HITL_THRESHOLD
        log.append(reason("locate_baustelle", REASONING_NARRATION,
                          f"Baustelle: {res.formatiert} → {res.breitengrad}, {res.laengengrad} "
                          f"(Konfidenz {res.konfidenz:.2f})."))
        out: dict = {"baustelle_breitengrad": str(res.breitengrad),
                     "baustelle_laengengrad": str(res.laengengrad),
                     "baustelle_adresse": res.formatiert,
                     "baustelle_status": BAUSTELLE_UNSICHER if unsicher else BAUSTELLE_OK}
        if unsicher:
            out["warnungen"] = [f"Standort '{res.formatiert}' nur grob geokodiert "
                                f"(Konfidenz {res.konfidenz:.2f}) — in Gate A prüfen."]
        angebote = await rang_lieferanten(bc, res.breitengrad, res.laengengrad)
        if angebote:
            out["lieferanten_vorschlag"] = {bc: {
                "default": angebote[0].code,
                "angebote": [a.model_dump(mode="json") for a in angebote]}}
            log.append(reason("locate_baustelle", REASONING_NARRATION,
                              f"{len(angebote)} Lieferant(en) für {bc} gerankt; günstigster: "
                              f"{angebote[0].name} ({angebote[0].frei_bau_eur_pro_t} €/t frei Baustelle)."))
        out["reasoning_log"] = log
        return out

    def method_review(state: PositionKalkulationState) -> dict:
        """Gate A: confirm (or correct) the Leistung and select the Bauverfahren before the
        worklist is derived (the worklist depends on the chosen recipe). The full Leistung
        catalog is offered so an unclassified position can still be assigned; cancel aborts."""
        lk = state["leistung_key"]
        kand = state["bauverfahren_kandidaten"]
        antwort = interrupt({
            "stage": STAGE_METHOD_REVIEW,
            "leistung_key": lk,
            "leistung_name": state.get("leistung_name"),
            "bauverfahren_kandidaten": kand,
            "bauverfahren_default": kand[0] if kand else None,
            "katalog": LEISTUNG_KATALOG,
            "bauverfahren_ressourcen": BAUVERFAHREN_RESSOURCEN,
            "baustoff_katalog": BAUSTOFF_KATALOG,
            "baustoff_vorschlag": state.get("baustoff_vorschlag"),
            "maschinen_default": state.get("maschinen_default") or {},
            "lieferanten_vorschlag": state.get("lieferanten_vorschlag") or {},
            "baustelle": {
                "adresse": state.get("baustelle_adresse"),
                "breitengrad": state.get("baustelle_breitengrad"),
                "laengengrad": state.get("baustelle_laengengrad"),
                "status": state.get("baustelle_status"),
            },
        }) or {}
        if antwort.get("cancel"):
            return {"abgebrochen": True,
                    "reasoning_log": [reason("method_review", REASONING_NARRATION,
                                             "Kalkulation vom Kalkulator abgebrochen.")]}
        confirmed_lk = antwort.get("leistung_key") or lk
        if confirmed_lk not in LEISTUNGEN:
            raise ValueError(f"unbekannte Leistung in Gate A: {confirmed_lk!r}")
        bv = waehle_bauverfahren(confirmed_lk, antwort.get("bauverfahren_key"))
        # Material: an explicit Gate A pick wins; else an above-threshold BM25 auto-match applies;
        # else whatever the LV position already carried.
        vorschlag = state.get("baustoff_vorschlag") or {}
        auto_baustoff = vorschlag.get("code") if vorschlag.get("auto") else None
        out = {
            "leistung_key": confirmed_lk,
            "bauverfahren_key": bv,
            # Resource picks (machines per slot, material, supplier) — bind_resources / bind_lieferant
            # auto-fill the rest. Supplier picks are keyed per material (baustoff_code).
            "gewaehlte_maschinen": antwort.get("maschinen") or {},
            "gewaehlter_lieferant": antwort.get("lieferanten") or {},
            # Manual Baustelle location override (address and/or coords); bind_lieferant resolves it.
            "baustelle_override": antwort.get("baustelle") or {},
            "baustoff_code": (antwort.get("baustoff_code") or auto_baustoff
                              or state["position"].get("baustoff_code")),
            "reasoning_log": [reason("method_review", REASONING_NARRATION,
                                     f"Leistung {confirmed_lk} bestätigt; Bauverfahren {bv} gewählt.")],
        }
        if confirmed_lk != lk:
            out["leistung_name"] = LEISTUNGEN[confirmed_lk].name
            out["bauverfahren_kandidaten"] = kandidaten(confirmed_lk)
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

    async def bind_lieferant(state: PositionKalkulationState) -> dict:
        """Finalize the supplier for the bound Baustoff: honour the Gate A pick iff that supplier
        carries the final material, else auto-pick cheapest-delivered (mirror of the machine-pick
        fallback). Stash the ex-works price override + the supplier road distance for compute/Gate B."""
        bc = state.get("baustoff_code")
        log = [reason("bind_lieferant", REASONING_NARRATION, "Lieferant für das Material festlegen.")]
        if not bc:
            log.append(reason("bind_lieferant", REASONING_NARRATION,
                              "Kein Material — Materialpreis aus Katalog."))
            return {"reasoning_log": log}

        # Resolve the site location: a Gate A manual override (coords, else address) wins; else the
        # auto-geocoded coords from locate_baustelle. Manual edits update the persisted location.
        override = state.get("baustelle_override") or {}
        out: dict = {}
        lat = lon = None
        o_lat, o_lon, o_adr = override.get("breitengrad"), override.get("laengengrad"), override.get("adresse")
        if o_lat and o_lon:
            try:
                lat, lon = Decimal(str(o_lat)), Decimal(str(o_lon))
                out.update({"baustelle_breitengrad": str(lat), "baustelle_laengengrad": str(lon),
                            "baustelle_status": BAUSTELLE_OK})
                log.append(reason("bind_lieferant", REASONING_NARRATION,
                                  f"Standort manuell gesetzt: {lat}, {lon}."))
            except InvalidOperation:
                log.append(reason("bind_lieferant", REASONING_NARRATION, "Manuelle Koordinaten ungültig."))
        elif o_adr and o_adr != state.get("baustelle_adresse"):
            try:
                res = await geocode(o_adr)
                lat, lon = res.breitengrad, res.laengengrad
                out.update({"baustelle_breitengrad": str(lat), "baustelle_laengengrad": str(lon),
                            "baustelle_adresse": res.formatiert, "baustelle_status": BAUSTELLE_OK})
                log.append(reason("bind_lieferant", REASONING_NARRATION,
                                  f"Adresse '{o_adr}' geokodiert: {res.formatiert} → {lat}, {lon}."))
            except MapsError as exc:
                log.append(reason("bind_lieferant", REASONING_NARRATION,
                                  f"Manuelle Adresse nicht geokodiert ({exc})."))
        if (lat is None or lon is None) and state.get("baustelle_breitengrad") and state.get("baustelle_laengengrad"):
            lat = Decimal(state["baustelle_breitengrad"])
            lon = Decimal(state["baustelle_laengengrad"])
        if lat is None or lon is None:
            log.append(reason("bind_lieferant", REASONING_NARRATION,
                              "Kein Standort — Materialpreis aus Katalog, Antransport per Default."))
            out["reasoning_log"] = log
            return out

        angebote = await rang_lieferanten(bc, lat, lon)
        if not angebote:
            log.append(reason("bind_lieferant", REASONING_NARRATION,
                              f"Kein Lieferant führt {bc} — Katalogpreis (frei Werk), Default-Antransport."))
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
        # Values bound before Gate B from a resource pick: machine rates/productivity + the supplier
        # haul distance. They become the Gate B proposal (collapsed, overridable) for their leaf.
        gebundene_werte = {**(state.get("maschinen_werte") or {}), **(state.get("lieferant_werte") or {})}
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
                wj = gebundene_werte[name]                # machine rate/productivity or supplier distance
                defn = KATALOG[name]
                v = VariablenVorschlag(name=name, bezeichnung=defn.bezeichnung, einheit=defn.einheit,
                                       art=art, hochrisiko=False, tier=TIER_COLLAPSED,
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
        """Gate B: every leaf shown (surfaced tier for decision, collapsed pre-accepted);
        accept/override each. The submit writes the confirmed `werte` the calc consumes."""
        vorschlaege = state["vorschlaege"]
        surfaced = [v for v in vorschlaege.values() if v["tier"] == TIER_SURFACED]
        collapsed = [v for v in vorschlaege.values() if v["tier"] == TIER_COLLAPSED]
        antwort = interrupt({
            "stage": STAGE_VARIABLE_REVIEW,
            "konfidenz_schwelle_review": state["konfidenz_schwelle_review"],
            "surfaced": surfaced,
            "collapsed": collapsed,
        }) or {}
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
            # Engine resolves SATZ/STAMMDATEN itself; only EINGABE values must be pre-filled.
            if v["art"] == BlattArt.EINGABE.value:
                if v["wert"] is None:
                    warnungen.append(f"{name} ({defn.bezeichnung}) ohne Wert bestätigt — "
                                     f"Kalkulation kann scheitern.")
                else:
                    werte[name] = wert_to_json(VariablenWert(
                        name=name, wert=Decimal(v["wert"]),
                        quelle=M(v["quelle"]) if v["quelle"] else M.HITL,
                        konfidenz=Decimal(v["konfidenz"]) if v["konfidenz"] else None,
                        beleg=v["beleg"]))
        return {
            "werte": werte,
            "vorschlaege": updated,
            "warnungen": warnungen,
            "reasoning_log": [reason("variable_review", REASONING_NARRATION,
                                     f"{ueberschrieben} Wert(e) überschrieben, übrige akzeptiert.")],
        }

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
    g.add_node("classify_leistung", classify_leistung)
    g.add_node("locate_baustelle", locate_baustelle)
    g.add_node("method_review", method_review)
    g.add_node("bind_resources", bind_resources)
    g.add_node("bind_lieferant", bind_lieferant)
    g.add_node("derive_required_variables", derive_required_variables)
    g.add_node("resolve_variables", resolve_variables)
    g.add_node("variable_review", variable_review)
    g.add_node("compute", compute)
    g.add_node("render_output", render_output)

    g.add_edge(START, "launch")
    g.add_edge("launch", "extract_chat_values")
    g.add_edge("extract_chat_values", "classify_leistung")
    g.add_edge("classify_leistung", "locate_baustelle")
    g.add_edge("locate_baustelle", "method_review")
    g.add_conditional_edges("method_review", _route_after_method,
                            ["bind_resources", END])
    g.add_edge("bind_resources", "bind_lieferant")
    g.add_edge("bind_lieferant", "derive_required_variables")
    g.add_edge("derive_required_variables", "resolve_variables")
    g.add_edge("resolve_variables", "variable_review")
    g.add_edge("variable_review", "compute")
    g.add_edge("compute", "render_output")
    g.add_edge("render_output", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
