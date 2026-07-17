"""
Store.py — assembler / entry point.

Wires the decomposed catalog into the runnable store and provides the calc
helpers. Each piece now lives in its own file (≈ one future table):

    kalkulation_model_v2  engine (models + Kalkulator + AST evaluator) materialien
    Baustoff catalog          lieferanten  suppliers lieferanten_preise    supplier
    price list        stammdaten   rate book + bridges kontext_variablen     situational
    vars + cascades formel       formulas ausfuehrungsarten · vorgaenge · bauverfahren ·
    leistungen · positionen
"""

from decimal import Decimal

from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M,
    Kalkulationskontext,
    Kalkulator,
    VariablenWert as Wert,
)
from shared.services.kalkulation_v2.materialien import BAUSTOFFE
from shared.services.kalkulation_v2.lieferanten import LIEFERANTEN
from shared.services.kalkulation_v2.lieferanten_preise import lade_preise
from shared.services.kalkulation_v2.stammdaten import STAMMDATEN_VARIABLEN
from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN
from shared.services.kalkulation_v2.formel import FORMELN
from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN
from shared.services.kalkulation_v2.vorgaenge import VORGAENGE
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN
from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.leistung_bauverfahren import waehle_bauverfahren
from shared.services.kalkulation_v2.positionen import POSITIONEN, Position
from datetime import date

STICHTAG = date(2026, 6, 22)

# Attach the static supplier price list to LIEFERANTEN[*].preise at catalog assembly, so
# the running agent's supplier ranking sees prices (lade_preise is otherwise only called
# in __main__).
lade_preise(BAUSTOFFE, LIEFERANTEN)

# Merge the variable catalog from its two sources (no key overlaps by design). Formeln
# are no variables any more — instanzen live on the Vorgang (rechnung).
KATALOG = {**STAMMDATEN_VARIABLEN, **KONTEXT_VARIABLEN}

GEOM = {
    "m2": "flaeche_m2",
    "m": "laenge_m",
    "m3": "volumen_m3",
    "t": "menge_t",
    "St": "anzahl_st",
}


def baue_kontext(pos: Position, einheit: str) -> Kalkulationskontext:
    stamm = {"baustoff": BAUSTOFFE[pos.baustoff_code]} if pos.baustoff_code else {}
    ctx = Kalkulationskontext(stichtag=STICHTAG, stammdaten=stamm)  # type: ignore
    ctx.werte[GEOM[einheit]] = Wert(
        name=GEOM[einheit],
        wert=pos.menge,
        quelle=M.LANGTEXT,
        beleg=f"LV Menge {pos.menge} {einheit}",
    )
    for name, wert in pos.kontext.items():
        ctx.werte[name] = Wert(
            name=name, wert=wert, quelle=M.RAG, konfidenz=Decimal("0.7")
        )
    return ctx


def kalkuliere_kontext(
    leistung_key: str, bauverfahren_key: str, ctx: Kalkulationskontext, menge: Decimal
) -> dict:
    """Run a chosen recipe against a pre-filled context — the StateGraph's resolved
    `werte` (inputs + booked geometry). After it returns, `ctx.werte` holds the full
    derivation tree (inputs, Stammdaten, Sätze, Formel-Zwischenwerte) for the Nachweis.
    """
    kalk = Kalkulator(KATALOG, FORMELN)
    leistung = LEISTUNGEN[leistung_key]  # the service (what)
    bauverfahren = BAUVERFAHREN[bauverfahren_key]  # selected recipe (how)
    ergebnisse = [v.kalkuliere(kalk, ctx) for v in bauverfahren.vorgaenge]
    ekt = sum((e["ekt_eur"] for e in ergebnisse), Decimal("0"))
    return {
        "leistung": leistung.name,
        "leistung_key": leistung_key,
        "einheit": leistung.einheit,
        "bauverfahren": bauverfahren_key,
        "ekt_eur": ekt,
        "ep_eur": (ekt / menge).quantize(Decimal("0.01")),
        "detail": ergebnisse,
    }


def kalkuliere(pos: Position) -> dict:
    bv_key = waehle_bauverfahren(
        pos.leistung_key, pos.bauverfahren_key
    )  # calculator picks
    ctx = baue_kontext(pos, LEISTUNGEN[pos.leistung_key].einheit)  # type: ignore
    return kalkuliere_kontext(pos.leistung_key, bv_key, ctx, pos.menge)


def build_store() -> dict:
    """Return the fully wired store for the API/StateGraph."""
    return {
        "katalog": KATALOG,
        "formeln": FORMELN,
        "baustoffe": BAUSTOFFE,
        "lieferanten": LIEFERANTEN,
        "ausfuehrungsarten": AUSFUEHRUNGSARTEN,
        "vorgaenge": VORGAENGE,
        "bauverfahren": BAUVERFAHREN,
        "leistungen": LEISTUNGEN,
        "positionen": POSITIONEN,
    }


if __name__ == "__main__":
    print(
        f"Katalog: {len(KATALOG)} Variablen · {len(FORMELN)} Formeln · "
        f"{len(VORGAENGE)} Vorgänge · "
        f"{len(AUSFUEHRUNGSARTEN)} Ausführungsarten · {len(BAUVERFAHREN)} Bauverfahren "
        f"· "
        f"{len(LEISTUNGEN)} Leistungen · {len(POSITIONEN)} Positionen\n"
    )
    print(f"{'OZ':<12}{'Leistung':<46}{'Menge':>9} {'EH':<4}{'EP €':>9}{'GP €':>12}")
    print("-" * 94)
    gesamt = Decimal("0")
    for pos in POSITIONEN:
        r = kalkuliere(pos)
        gesamt += r["ekt_eur"]
        print(
            f"{pos.oz:<12}{r['leistung'][:44]:<46}{pos.menge:>9} {r['einheit']:<4}"
            f"{r['ep_eur']:>9}{r['ekt_eur'].quantize(Decimal('0.01')):>12}"
        )
    print("-" * 94)
    print(f"{'EKT gesamt (Bauabschnitt 01)':<71}{gesamt.quantize(Decimal('0.01')):>23}")

    # --- Recipe selection in action: L_AUFBRECHEN has two candidate Bauverfahren ---
    from shared.services.kalkulation_v2.leistung_bauverfahren import kandidaten
    from copy import deepcopy

    auf = next(p for p in POSITIONEN if p.leistung_key == "L_AUFBRECHEN")
    print(
        f"\nKalkulator-Auswahl für '{LEISTUNGEN['L_AUFBRECHEN'].name}' "
        f"(Kandidaten: {kandidaten('L_AUFBRECHEN')}):"
    )
    for bv in kandidaten("L_AUFBRECHEN"):
        probe = deepcopy(auf)
        probe.bauverfahren_key = bv
        r = kalkuliere(probe)
        marke = "  <- Default" if bv == kandidaten("L_AUFBRECHEN")[0] else ""
        print(
            f"   {bv:<12} EP {r['ep_eur']:>7} €/{r['einheit']}   GP "
            f"{r['ekt_eur'].quantize(Decimal('0.01')):>10} €{marke}"
        )
