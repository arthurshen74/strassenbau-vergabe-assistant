"""
leistung_bauverfahren.py — Leistung → candidate Bauverfahren mapping (join table).

This is the set of recipes the calculator may choose FROM to fulfil a Leistung. Most
Leistungen have one candidate; where there are several, the choice is the calculator's
(StateGraph) decision, driven by machinery/access/the bidder's kit. The first candidate
is the default. Validated at import: every Leistung has at least one candidate and every
candidate is a real Bauverfahren.

Exports LEISTUNG_BAUVERFAHREN, kandidaten(), waehle_bauverfahren().
"""

from shared.services.kalkulation_v2.leistungen import LEISTUNGEN
from shared.services.kalkulation_v2.bauverfahren import BAUVERFAHREN

# leistung_code -> ordered list of candidate Bauverfahren keys (first = default). Where
# a generic Leistung has several recipes, the choice is the calculator's (e.g.
# L_REINIGEN: Kehrmaschine vs Hochdruck; L_FSS: Grader vs Fertiger).
LEISTUNG_BAUVERFAHREN: dict[str, list[str]] = {
    "L_BANKETT_ABTRAGEN": ["BV_BODENABTRAG"],
    "L_BODEN_EINBAU_GROBK": ["BV_BODEN_GROBK"],
    "L_BANKETTBEF": ["BV_BANKETT_GRADER", "BV_BANKETT_FERTIGER"],
    "L_OBERBODEN": ["BV_OBERBODEN_GRADER", "BV_OBERBODEN_HAND"],
    "L_ERSCHWERNIS_FRAESEN": ["BV_ERSCHWERNIS"],
    "L_ERSCHWERNIS_ASPHALT": ["BV_ERSCHWERNIS"],
    "L_MARKIERUNG": ["BV_MARKIERUNG"],
    "L_TRENNEN": ["BV_SCHNEIDEN"],
    "L_FRAESEN": ["BV_FRAESEN"],
    # two ways to take up the asphalt: break it out (default) or mill it out
    "L_AUFBRECHEN": ["BV_AUFBRECHEN", "BV_FRAESEN"],
    "L_BODEN_LOESEN": ["BV_BODENABTRAG"],
    "L_PLANUM": ["BV_PLANUM", "BV_PLANUM_VERDICHTEN"],
    "L_BODEN_VERDICHTEN": ["BV_VERDICHTEN"],
    "L_FSS": ["BV_FSS_GRADER", "BV_FSS_FERTIGER"],
    "L_ASPHALTTRAGSCHICHT": ["BV_ASPHALT_EINBAU"],
    "L_NAHT": ["BV_NAHT"],
    "L_REINIGEN": ["BV_REINIGEN_KEHREN", "BV_REINIGEN_HD"],
    "L_ANSPRITZEN": ["BV_ANSPRITZEN"],
    "L_ASPHALTEINLAGE": ["BV_GRID"],
    "L_ASPHALTBINDER": ["BV_ASPHALT_EINBAU"],
    "L_ASPHALTDECK": ["BV_ASPHALT_EINBAU"],
    "L_ABSTUMPFUNG": ["BV_ABSTUMPFEN"],
    "L_KEHREN_VSM": ["BV_REINIGEN_KEHREN"],
    "L_NAHT_AUFWEITEN": ["BV_NAHT_AUFWEITEN"],
    "L_FUGENFUELLUNG_N2": ["BV_FUGENFUELLUNG"],
    # --- distinct ops (own recipe / function) ---
    "L_FEINFRAESEN": ["BV_FEINFRAESEN"],
    "L_ASPHALT_HAND": ["BV_ASPHALT_HAND"],
    "L_GUSSASPHALT_DECK": ["BV_GUSSASPHALT"],
    "L_STS": ["BV_FSS_GRADER", "BV_FSS_FERTIGER"],
    "L_DSK": ["BV_DSK"],
    "L_RANDABDICHTUNG": ["BV_RANDABDICHTUNG"],
}


def kandidaten(leistung_key: str) -> list[str]:
    return LEISTUNG_BAUVERFAHREN.get(leistung_key, [])


def waehle_bauverfahren(leistung_key: str, praeferenz: str | None = None) -> str:
    """Pick a Bauverfahren for a Leistung. Honour an explicit preference if it is a
    valid candidate; otherwise return the default (first) candidate."""
    kand = kandidaten(leistung_key)
    if not kand:
        raise ValueError(
            f"Leistung '{leistung_key}' hat keine Bauverfahren-Kandidaten."
        )
    if praeferenz is not None:
        if praeferenz not in kand:
            raise ValueError(
                f"'{praeferenz}' ist kein Kandidat für '{leistung_key}' (erlaubt: "
                f"{kand})."
            )
        return praeferenz
    return kand[0]


def validate() -> list[str]:
    fehler: list[str] = []
    for lk in LEISTUNGEN:
        if not kandidaten(lk):
            fehler.append(f"Leistung ohne Bauverfahren-Kandidaten: {lk}")
    for lk, kand in LEISTUNG_BAUVERFAHREN.items():
        if lk not in LEISTUNGEN:
            fehler.append(f"Mapping verweist auf unbekannte Leistung: {lk}")
        for bk in kand:
            if bk not in BAUVERFAHREN:
                fehler.append(f"Unbekanntes Bauverfahren '{bk}' bei {lk}")
    return fehler


_fehler = validate()
if _fehler:
    raise ValueError(
        "Ungültiges Leistung→Bauverfahren-Mapping:\n  " + "\n  ".join(_fehler)
    )


if __name__ == "__main__":
    print(f"{len(LEISTUNG_BAUVERFAHREN)} Leistungen gemappt, alle Kandidaten gültig.\n")
    print(
        "Leistungen mit mehreren Bauverfahren-Kandidaten (Auswahl trifft der "
        "Kalkulator):"
    )
    for lk, kand in LEISTUNG_BAUVERFAHREN.items():
        if len(kand) > 1:
            print(f"  {lk:<22} -> {kand}  (Default: {kand[0]})")
