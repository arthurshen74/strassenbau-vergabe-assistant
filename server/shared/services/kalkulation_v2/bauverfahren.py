"""
bauverfahren.py — the Bauverfahren catalog (the recipes).

A Bauverfahren is a process the calculator may select to fulfil a Leistung. Each is
an explicit, authored recipe: an ordered list of one or more Vorgänge (referenced by
key from VORGAENGE). This is a STATIC catalog — it is NOT derived from VORGAENGE; the
fact that most recipes happen to contain a single Vorgang today is incidental, and a
recipe is free to chain several. Exports BAUVERFAHREN.
"""

from model import Bauverfahren
from vorgaenge import VORGAENGE


def _bv(code, name, *vorgang_keys) -> Bauverfahren:
    return Bauverfahren(code=code, name=name, vorgaenge=[VORGAENGE[k] for k in vorgang_keys])


BAUVERFAHREN: dict[str, Bauverfahren] = {
    "BV_BODENABTRAG":    _bv("BV_BODENABTRAG",    "Bodenabtrag maschinell, Bagger + Abtransport",        "BODENABTRAG"),
    "BV_EINBAU":         _bv("BV_EINBAU",         "Mineralstoffeinbau maschinell, Radlader + Walze",     "EINBAU"),
    "BV_ERSCHWERNIS":    _bv("BV_ERSCHWERNIS",    "Erschwernis-Zulage Einfassungen",                     "ERSCHWERNIS"),
    "BV_MARKIERUNG":     _bv("BV_MARKIERUNG",     "Markierung entfernen, Markierungsfräse",              "MARKIERUNG"),
    "BV_SCHNEIDEN":      _bv("BV_SCHNEIDEN",      "Asphalt trennen, Fugenschneider",                     "SCHNEIDEN"),
    "BV_FRAESEN":        _bv("BV_FRAESEN",        "Asphalt fräsen, Kaltfräse",                           "FRAESEN"),
    "BV_AUFBRECHEN":     _bv("BV_AUFBRECHEN",     "Asphalt aufbrechen und aufnehmen, Bagger m. Meißel",  "AUFBRECHEN"),
    "BV_PLANUM":         _bv("BV_PLANUM",         "Planum herstellen, Grader + Walze",                   "PLANUM"),
    "BV_VERDICHTEN":     _bv("BV_VERDICHTEN",     "Boden verdichten, Walze",                             "VERDICHTEN"),
    "BV_ASPHALT_EINBAU": _bv("BV_ASPHALT_EINBAU", "Asphalttragschicht einbauen, Fertiger + Walze",       "ASPHALT_EINBAU"),
    "BV_NAHT":           _bv("BV_NAHT",           "Naht herstellen, PmB-Fugenband",                      "NAHT"),
}