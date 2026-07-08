"""
worklist.py — derive the resolution worklist for a chosen Bauverfahren.

`benoetigte_variablen` walks a recipe's Vorgänge -> rechnung bindings down to every
resolution leaf: extracted inputs (Eingabe), rate-book constants (Satz), and
master-data lookups (Stammdaten). `formel.<instanz>` references are walked through,
not returned; literals and `baustoff.*` fields are no variables. This is the data
the StateGraph's variable-review gate consumes; the engine derives it so the graph
topology stays position-agnostic.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    Bauverfahren,
    FormelInstanz,
    Kalkulator,
    VariableDefinition,
    Vorgang,
)


class BlattArt(str, Enum):
    EINGABE = "eingabe"          # extracted input (LANGTEXT/RAG/HITL, maybe + default)
    SATZ = "satz"                # KONSTANTE rate book
    STAMMDATEN = "stammdaten"    # master-data lookup


class VariablenBlatt(BaseModel):
    """One resolution leaf the calc will consume, with what the review needs to show."""
    model_config = ConfigDict(extra="forbid")

    name: str
    art: BlattArt
    bezeichnung: str
    einheit: str | None = None
    # High-stakes: an extracted input with no KONSTANTE fallback (e.g. fraesgut_klasse).
    hochrisiko: bool = False


_EINGABE_METHODEN = {
    AufloesungsMethode.LANGTEXT,
    AufloesungsMethode.RAG,
    AufloesungsMethode.HITL,
}

_VARIABLEN_PRAEFIXE = ("kontext.", "stammdaten.")


def _blatt(defn: VariableDefinition) -> VariablenBlatt:
    methoden = {s.methode for s in defn.aufloesung}
    if methoden & _EINGABE_METHODEN:
        art = BlattArt.EINGABE
        hochrisiko = AufloesungsMethode.KONSTANTE not in methoden
    elif AufloesungsMethode.STAMMDATEN in methoden:
        art = BlattArt.STAMMDATEN
        hochrisiko = False
    else:
        art = BlattArt.SATZ
        hochrisiko = False
    return VariablenBlatt(
        name=defn.name,
        art=art,
        bezeichnung=defn.bezeichnung,
        einheit=defn.einheit,
        hochrisiko=hochrisiko,
    )


def benoetigte_variablen(
    bauverfahren: Bauverfahren,
    kalk: Kalkulator,
    *,
    gebucht: frozenset[str] = frozenset(),
) -> list[VariablenBlatt]:
    """All resolution leaves the recipe consumes, in first-seen order.

    `formel.<instanz>` references are recursed through, not returned. Names in
    `gebucht` (booked directly, e.g. the geometry variable filled from the LV Menge)
    terminate the walk and are excluded — they are already resolved.
    """
    blaetter: dict[str, VariablenBlatt] = {}
    besucht: set[str] = set()

    def besuche_variable(name: str) -> None:
        if name in besucht or name in gebucht:
            return
        besucht.add(name)
        defn = kalk.katalog.get(name)
        if defn is None:
            raise KeyError(f"Variable nicht im Katalog: {name}")
        blaetter[name] = _blatt(defn)

    def besuche_instanz(vorgang: Vorgang, inst: FormelInstanz) -> None:
        # A booked materialized variable preempts the whole instanz at calc time, so its
        # inputs are never consumed (a t-billed position must not ask for Einbaudicke).
        if inst.variable and inst.variable in gebucht:
            return
        for pfad in inst.bindung.values():
            praefix, _, rest = pfad.partition(".")
            if f"{praefix}." in _VARIABLEN_PRAEFIXE and rest:
                besuche_variable(rest)
            elif praefix == "formel" and rest:
                besuche_instanz(vorgang, vorgang.rechnung.instanzen[rest])
            # baustoff.* fields and literals are not variables.

    for vorgang in bauverfahren.vorgaenge:
        for instanzen in vorgang.rechnung.kosten.values():
            for inst in instanzen:
                besuche_instanz(vorgang, inst)
    return list(blaetter.values())


def braucht_baustoff(bauverfahren: Bauverfahren, kalk: Kalkulator) -> bool:
    """True if the recipe consumes a graded Baustoff — i.e. a leaf reads a `baustoff.*`
    master-data field (density/compaction for tonnage). Recipes that price material directly
    per m²/t (DSK, Gussasphalt) or use no material (Fräsen) return False, so no Baustoff is
    offered for them."""
    for blatt in benoetigte_variablen(bauverfahren, kalk):
        if blatt.art != BlattArt.STAMMDATEN:
            continue
        for schritt in kalk.katalog[blatt.name].aufloesung:
            if (schritt.methode == AufloesungsMethode.STAMMDATEN
                    and (schritt.stammdaten_pfad or "").startswith("baustoff.")):
                return True
    return False
