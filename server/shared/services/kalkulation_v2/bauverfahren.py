"""
bauverfahren.py — the Bauverfahren catalog (the recipes).

A Bauverfahren is a process the calculator may select to fulfil a Leistung. Each is
an explicit, authored recipe: an ordered list of one or more Vorgänge (referenced by
key from VORGAENGE). This is a STATIC catalog — it is NOT derived from VORGAENGE; the
fact that most recipes happen to contain a single Vorgang today is incidental, and a
recipe is free to chain several. Exports BAUVERFAHREN.
"""

from shared.services.kalkulation_v2.model import Bauverfahren
from shared.services.kalkulation_v2.vorgaenge import VORGAENGE


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
    "BV_PLANUM_VERDICHTEN": _bv("BV_PLANUM_VERDICHTEN", "Planum herstellen und verdichten, Grader + Walze",
                                "PLANUM", "VERDICHTEN"),  # multi-Vorgang: both steps work off flaeche_m2
    "BV_VERDICHTEN":     _bv("BV_VERDICHTEN",     "Boden verdichten, Walze",                             "VERDICHTEN"),
    "BV_ASPHALT_EINBAU": _bv("BV_ASPHALT_EINBAU", "Asphalttragschicht einbauen, Fertiger + Walze",       "ASPHALT_EINBAU"),
    "BV_NAHT":           _bv("BV_NAHT",           "Naht herstellen, PmB-Fugenband",                      "NAHT"),
    # --- FSS: two machinery-driven recipes; compaction (FSS_VERDICHTEN) is identical in both ---
    "BV_FSS_GRADER":   _bv("BV_FSS_GRADER",   "FSS: Radlader legen + Grader profilieren + Walze",
                           "FSS_LEGEN", "FSS_PROFIL", "FSS_VERDICHTEN"),
    "BV_FSS_FERTIGER": _bv("BV_FSS_FERTIGER", "FSS: Fertiger (legen+abziehen) + Walze",
                           "FSS_FERTIGER", "FSS_VERDICHTEN"),
    # --- Bankettbefestigung: two machinery-driven recipes; compaction identical in both ---
    "BV_BANKETT_GRADER":   _bv("BV_BANKETT_GRADER",   "Bankett: Radlader legen + Grader profilieren + Tandemwalze",
                               "BANKETT_LEGEN", "BANKETT_PROFIL", "BANKETT_VERDICHTEN"),
    "BV_BANKETT_FERTIGER": _bv("BV_BANKETT_FERTIGER", "Bankett: Bankettfertiger (legen+profilieren) + Tandemwalze",
                               "BANKETT_FERTIGER", "BANKETT_VERDICHTEN"),
    # --- Grobkörniger Boden: single recipe (bulk subgrade fill; no paver fork) ---
    "BV_BODEN_GROBK": _bv("BV_BODEN_GROBK", "Grobk. Boden: liefern/legen + profilieren (Planum) + verdichten",
                          "BODEN_GROBK_LEGEN", "BODEN_GROBK_PROFIL", "BODEN_GROBK_VERDICHTEN"),
    # --- Oberboden andecken: no compaction; hand default, grader alternative ---
    "BV_OBERBODEN_HAND":   _bv("BV_OBERBODEN_HAND",   "Oberboden andecken von Hand (Kolonne), ohne Verdichtung",
                               "OBERBODEN_HAND"),
    "BV_OBERBODEN_GRADER": _bv("BV_OBERBODEN_GRADER", "Oberboden andecken mit Grader, ohne Verdichtung",
                               "OBERBODEN_GRADER"),
    # --- Unterlage reinigen: one prescribed method each ---
    "BV_REINIGEN_KEHREN": _bv("BV_REINIGEN_KEHREN", "Unterlage reinigen, selbstaufnehmende Kehrmaschine", "REINIGEN_KEHREN"),
    "BV_REINIGEN_HD":     _bv("BV_REINIGEN_HD",     "Unterlage reinigen, Hochdruck-Wasch-Sauganlage", "REINIGEN_HD"),
    "BV_ANSPRITZEN":      _bv("BV_ANSPRITZEN",      "Bitumenemulsion aufsprühen (Schichtenverbund)", "ANSPRITZEN"),
    "BV_GRID":            _bv("BV_GRID",            "Asphalteinlage liefern und verlegen", "GRID_EINBAU"),
    "BV_ABSTUMPFEN":      _bv("BV_ABSTUMPFEN",      "Abstumpfung aufbringen und einwalzen", "ABSTUMPFEN"),
    "BV_NAHT_AUFWEITEN":  _bv("BV_NAHT_AUFWEITEN",  "Naht/Anschluss zur Fuge aufweiten", "NAHT_AUFWEITEN"),
    "BV_FUGENFUELLUNG":   _bv("BV_FUGENFUELLUNG",   "Fugenfüllung herstellen (Fugenmasse N2)", "FUGENFUELLUNG"),
}