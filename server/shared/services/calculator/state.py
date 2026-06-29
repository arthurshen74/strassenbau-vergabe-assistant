"""State envelope + output artifacts for the EKT position-calculation graph.

The graph state is the chat+calc envelope; its heart is the resolved-values dict
(`werte`) the engine consumes, but it also carries the method decision (Gate A),
the variable worklist + proposals (Gate B), and the three output artifacts. State
is kept plain-JSON (no Decimal, no engine objects) so the LangGraph Postgres
checkpointer can serialize it across HITL interrupts; the compute node rebuilds the
engine's `VariablenWert` bag from `werte` and dumps results back as JSON.
"""

from __future__ import annotations

import operator
from decimal import Decimal
from typing import Annotated, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.services.kalkulation_v2.model import AufloesungsMethode, VariablenWert

# Default confidence threshold for Gate B tiering (ARCHITECTURE §7).
DEFAULT_REVIEW_SCHWELLE = 0.75

# Interrupt payload stages (the UI dispatches its gate components on these).
STAGE_METHOD_REVIEW = "method_review"
STAGE_VARIABLE_REVIEW = "variable_review"

# Gate B presentation tiers + per-variable review status.
TIER_SURFACED = "surfaced"
TIER_COLLAPSED = "collapsed"
STATUS_VORGESCHLAGEN = "vorgeschlagen"
STATUS_AKZEPTIERT = "akzeptiert"
STATUS_UEBERSCHRIEBEN = "ueberschrieben"


def wert_to_json(w: VariablenWert) -> dict:
    return {
        "name": w.name,
        "wert": str(w.wert),
        "quelle": w.quelle.value,
        "konfidenz": None if w.konfidenz is None else str(w.konfidenz),
        "beleg": w.beleg,
    }


def wert_from_json(d: dict) -> VariablenWert:
    return VariablenWert(
        name=d["name"],
        wert=Decimal(d["wert"]),
        quelle=AufloesungsMethode(d["quelle"]),
        konfidenz=None if d.get("konfidenz") is None else Decimal(d["konfidenz"]),
        beleg=d.get("beleg"),
    )


class VariablenVorschlag(BaseModel):
    """One Gate B row: a worklist leaf with its proposed value, provenance and tier."""
    model_config = ConfigDict(extra="forbid")

    name: str
    bezeichnung: str
    einheit: str | None = None
    art: str                                 # BlattArt value: eingabe | satz | stammdaten
    hochrisiko: bool = False
    tier: str = TIER_COLLAPSED
    status: str = STATUS_VORGESCHLAGEN
    # Proposed value + provenance; wert None when nothing was resolved (needs HITL).
    wert: str | None = None
    quelle: str | None = None
    konfidenz: str | None = None
    beleg: str | None = None


class NachweisZeile(BaseModel):
    """One row of the derivation tree: a variable the calc touched, with provenance.
    For FORMEL variables `ausdruck` + `eingaben` show how it was computed."""
    model_config = ConfigDict(extra="forbid")

    name: str
    bezeichnung: str | None = None
    wert: Decimal
    einheit: str | None = None
    quelle: str
    beleg: str | None = None
    ausdruck: str | None = None
    eingaben: list[str] | None = None


class KostenLinie(BaseModel):
    """One cost line of the EKT: a Kostenart of a Vorgang, with its variable + source."""
    model_config = ConfigDict(extra="forbid")

    vorgang: str
    kostenart: str
    variable: str
    betrag_eur: Decimal
    quelle: str


class EKTZeile(BaseModel):
    """The unit-price result for one position (EKT/Einzelkosten der Teilleistung)."""
    model_config = ConfigDict(extra="forbid")

    oz: str
    leistung_key: str
    leistung: str
    bauverfahren: str
    einheit: str | None = None
    menge: Decimal
    ep_eur: Decimal                          # Einheitspreis (per unit)
    gp_eur: Decimal                          # Gesamtpreis (EKT total for the menge)
    kostenlinien: list[KostenLinie] = []


class PositionKalkulationState(TypedDict, total=False):
    # --- permanent LV context (from the chat agent) ---
    position: dict                           # oz, kurztext, langtext, menge, einheit, baustoff_code
    project_uuid: UUID
    conversation_uuid: UUID
    chat_verlauf: list[dict]                 # [{role, content}] pre-launch transcript (source 0)
    vorgaben: dict                           # name -> value stated in chat (mock source-0 seed)

    # --- config ---
    konfidenz_schwelle_review: float

    # --- method decision (Gate A) ---
    leistung_key: str
    leistung_name: str
    bauverfahren_kandidaten: list[str]
    bauverfahren_key: str
    abgebrochen: bool                        # the Kalkulator cancelled at Gate A

    # --- resources (machines + material), bound after the recipe is chosen ---
    gewaehlte_maschinen: dict                # ausfuehrungsart_code -> Maschine code
    maschinen_default: dict                  # ausfuehrungsart_code -> right-sized default code
    maschinen_kandidaten: dict               # ausfuehrungsart_code -> [{code, hersteller, modell}]
    maschinen_werte: dict                    # name -> wert_to_json (machine-sourced cost/productivity)
    baustoff_code: str | None
    # BM25 match from the LV text -> Baustoff catalog (pre-fills the Gate A picker).
    # {code, name, konfidenz, auto, treffer:[{code,name,score}]}; None if the recipe needs none.
    baustoff_vorschlag: dict | None

    # --- Baustelle location + supplier selection ---
    baustelle_breitengrad: str               # geocoded site latitude (Decimal as string)
    baustelle_laengengrad: str               # geocoded site longitude (Decimal as string)
    # baustoff_code -> {default: lieferant_code|None, angebote: [LieferantAngebot.model_dump(json)]}.
    # Ranked cheapest-delivered for the Gate A per-material supplier picker.
    lieferanten_vorschlag: dict
    gewaehlter_lieferant: dict               # baustoff_code -> lieferant_code (Gate A pick)
    lieferant_code: str | None               # finalized supplier for the bound Baustoff
    lieferant_werkspreis: str | None         # finalized ex-works €/t override (string); None = catalog price
    lieferant_beleg: str | None              # Nachweis beleg for the supplier-driven material price
    lieferant_werte: dict                    # name -> wert_to_json (supplier-sourced, e.g. entfernung_lieferant_km)

    # --- resolution (Gate B) ---
    chat_werte: dict                         # name -> wert_to_json: values pinned from chat
    benoetigte: list[dict]                   # VariablenBlatt.model_dump() worklist leaves
    vorschlaege: dict                        # name -> VariablenVorschlag.model_dump()

    # --- outputs ---
    werte: dict                              # name -> wert_to_json -> Kalkulationskontext.werte
    ekt_zeile: dict                          # EKTZeile.model_dump(mode="json")
    nachweis_tabelle: list[dict]             # NachweisZeile.model_dump(mode="json")
    beschreibung: str | None
    warnungen: Annotated[list[str], operator.add]
    reasoning_log: Annotated[list[dict], operator.add]
