"""
binden.py — apply selected machines to a recipe's cost computation.

Given a Vorgang's machine binding (betriebsart_code, leistung_instanz, and
kosten_bindung: stammdaten rate variable -> machine property key) and a chosen Maschine,
produce the VariablenWert entries the calc consumes: the Stammdaten rate variables are
overridden from the property bag (a profile-specific override wins; global ctx hit), and
the productivity from the machine's Leistungsprofil overrides the Vorgang's leistung
instanz (Vorgang-scoped ctx hit). The StateGraph writes these into `ctx.werte`
(machine-sourced, shown collapsed in Gate B); a slot with no machine — or a machine
missing the needed profile/property — leaves the entry unfilled, so the calc falls back
to the Stammdaten default / the Kurven-Instanz.
"""

from __future__ import annotations

from decimal import Decimal

from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M,
    Bauverfahren,
    Maschine,
    VariablenWert,
    Vorgang,
)


def maschinen_werte(vorgang: Vorgang, maschine: Maschine) -> dict[str, VariablenWert]:
    """The ctx.werte entries a bound machine supplies for one Vorgang."""
    werte: dict[str, VariablenWert] = {}
    beleg = f"{maschine.hersteller} {maschine.modell}"
    profil = maschine.leistung_fuer(vorgang.betriebsart_code) if vorgang.betriebsart_code else None

    for cost_var, prop_key in (vorgang.kosten_bindung or {}).items():
        mw = (profil.eigenschaften.get(prop_key) if profil else None) or maschine.eigenschaft(prop_key)
        if mw is not None and isinstance(mw.wert, Decimal):
            werte[cost_var] = VariablenWert(name=cost_var, wert=mw.wert, quelle=M.STAMMDATEN, beleg=beleg)

    if vorgang.leistung_instanz and profil is not None:
        scoped = vorgang.instanz_scope(vorgang.leistung_instanz)
        werte[scoped] = VariablenWert(
            name=scoped, wert=profil.leistung, quelle=M.STAMMDATEN,
            beleg=f"{beleg} ({vorgang.betriebsart_code})")
    return werte


def rezept_maschinen_werte(
    bauverfahren: Bauverfahren, auswahl: dict[str, Maschine]
) -> dict[str, VariablenWert]:
    """All machine-sourced ctx.werte for a recipe, given a {ausfuehrungsart_code -> Maschine}
    selection. Slots without a selected machine are skipped (fall to default / HITL)."""
    werte: dict[str, VariablenWert] = {}
    for vorgang in bauverfahren.vorgaenge:
        aa = vorgang.ausfuehrungsart.code if vorgang.ausfuehrungsart is not None else None
        maschine = auswahl.get(aa) if aa else None
        if maschine is not None:
            werte.update(maschinen_werte(vorgang, maschine))
    return werte
