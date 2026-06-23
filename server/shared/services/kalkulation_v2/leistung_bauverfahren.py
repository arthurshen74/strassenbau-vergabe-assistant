"""
leistung_bauverfahren.py — Leistung → candidate Bauverfahren mapping (join table).

This is the set of recipes the calculator may choose FROM to fulfil a Leistung.
Most Leistungen have one candidate; where there are several, the choice is the
calculator's (StateGraph) decision, driven by machinery/access/the bidder's kit.
The first candidate is the default. Validated at import: every Leistung has at
least one candidate and every candidate is a real Bauverfahren.

Exports LEISTUNG_BAUVERFAHREN, kandidaten(), waehle_bauverfahren().
"""

from leistungen import LEISTUNGEN
from bauverfahren import BAUVERFAHREN

# leistung_code -> ordered list of candidate Bauverfahren keys (first = default)
LEISTUNG_BAUVERFAHREN: dict[str, list[str]] = {
    "L_BANKETT_ABTRAGEN":   ["BV_BODENABTRAG"],
    "L_BODEN_EINBAU_GROBK": ["BV_EINBAU"],
    "L_BANKETTBEF_B2":      ["BV_EINBAU"],
    "L_OBERBODEN":          ["BV_EINBAU"],
    "L_ERSCHWERNIS_FRAESEN": ["BV_ERSCHWERNIS"],
    "L_ERSCHWERNIS_ASPHALT": ["BV_ERSCHWERNIS"],
    "L_MARK_FARBE":         ["BV_MARKIERUNG"],
    "L_MARK_PLASTIK":       ["BV_MARKIERUNG"],
    "L_TRENNEN_QUER_DECK":  ["BV_SCHNEIDEN"],
    "L_TRENNEN_QUER_BINDER": ["BV_SCHNEIDEN"],
    "L_FRAESEN_1_25":       ["BV_FRAESEN"],
    "L_FRAESEN_3_45":       ["BV_FRAESEN"],
    "L_FRAESEN_5_9":        ["BV_FRAESEN"],
    "L_NACHFRAESEN":        ["BV_FRAESEN"],
    "L_TRENNEN_LAENGS":     ["BV_SCHNEIDEN"],
    # two ways to take up the asphalt: break it out (default) or mill it out
    "L_AUFBRECHEN":         ["BV_AUFBRECHEN", "BV_FRAESEN"],
    "L_BODEN_LOESEN":       ["BV_BODENABTRAG"],
    "L_PLANUM":             ["BV_PLANUM"],
    "L_PLANUM_VERDICHTET":  ["BV_PLANUM_VERDICHTEN"],
    "L_BODEN_VERDICHTEN":   ["BV_VERDICHTEN"],
    "L_FSS_EV45":           ["BV_FSS_GRADER", "BV_FSS_FERTIGER"],
    "L_ASPHALTTRAGSCHICHT": ["BV_ASPHALT_EINBAU"],
    "L_NAHT":               ["BV_NAHT"],
    "L_FSS_EV100":          ["BV_FSS_GRADER", "BV_FSS_FERTIGER"],
}


def kandidaten(leistung_key: str) -> list[str]:
    return LEISTUNG_BAUVERFAHREN.get(leistung_key, [])


def waehle_bauverfahren(leistung_key: str, praeferenz: str | None = None) -> str:
    """Pick a Bauverfahren for a Leistung. Honour an explicit preference if it is a
    valid candidate; otherwise return the default (first) candidate."""
    kand = kandidaten(leistung_key)
    if not kand:
        raise ValueError(f"Leistung '{leistung_key}' hat keine Bauverfahren-Kandidaten.")
    if praeferenz is not None:
        if praeferenz not in kand:
            raise ValueError(f"'{praeferenz}' ist kein Kandidat für '{leistung_key}' (erlaubt: {kand}).")
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
    raise ValueError("Ungültiges Leistung→Bauverfahren-Mapping:\n  " + "\n  ".join(_fehler))


if __name__ == "__main__":
    print(f"{len(LEISTUNG_BAUVERFAHREN)} Leistungen gemappt, alle Kandidaten gültig.\n")
    print("Leistungen mit mehreren Bauverfahren-Kandidaten (Auswahl trifft der Kalkulator):")
    for lk, kand in LEISTUNG_BAUVERFAHREN.items():
        if len(kand) > 1:
            print(f"  {lk:<22} -> {kand}  (Default: {kand[0]})")