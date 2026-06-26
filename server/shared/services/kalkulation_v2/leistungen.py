"""
leistungen.py — the Leistung catalog (generic work types).

A Leistung names the WORK, not the recipe or the material: "Asphalt fräsen",
"Frostschutzschicht herstellen", "Asphaltdeckschicht herstellen". It carries a
code, a description and an Einheit — nothing more. It does NOT reference a
Bauverfahren (the calculator selects one of the Leistung's candidates at calc
time), and it does NOT bake in the material/grade, depth, Ev2 target, method or
orientation: those are selections (Baustoff, Bauverfahren) or context values
(tiefe_cm, ev2_ziel, …) on the Position. So one Leistung covers what STLB splits
across many STLB-Nummern — e.g. the fräsen depths all resolve to the Kaltfräse
recipe with the depth as context; the asphalt mixes are a Baustoff choice on the
layer Leistung. Exports LEISTUNGEN.
"""

from shared.services.kalkulation_v2.model import Leistung


def L(code, name, einheit, stlb=None):
    return Leistung(code=code, name=name, einheit=einheit, standard_kennung=stlb)


LEISTUNGEN: dict[str, Leistung] = {l.code: l for l in [
    # --- 01.00 Erdbau / Bankett ---
    L("L_BANKETT_ABTRAGEN", "Bankett abtragen und schälen", "m3"),
    L("L_BODEN_EINBAU_GROBK", "Grobkörnigen Boden liefern und einbauen", "m3"),
    L("L_BANKETTBEF", "Bankettbefestigung herstellen", "m3"),
    L("L_OBERBODEN", "Oberboden liefern und andecken", "m3"),
    # --- 01.01 Erschwernisse ---
    L("L_ERSCHWERNIS_FRAESEN", "Erschwernis Einfassungen (Fräsen/Aufnehmen)", "m", "2231130839503"),
    L("L_ERSCHWERNIS_ASPHALT", "Erschwernis Einfassungen (Asphaltschichten)", "m", "2231130839503"),
    # --- 01.02 Markierung / Asphalt trennen + fräsen ---
    L("L_MARKIERUNG", "Längsmarkierung entfernen", "m", "22113100511111001"),
    L("L_TRENNEN", "Asphaltbefestigung trennen (Schnitt)", "m", "2231130382109"),
    L("L_FRAESEN", "Asphalt fräsen", "m2", "22311300510909010"),
    L("L_AUFBRECHEN", "Asphaltbefestigung aufnehmen, Randstreifen m. SoB", "m2", "22311302831909003"),
    # --- 01.03 Verbreiterungs-/Stützstreifen ---
    L("L_BODEN_LOESEN", "Boden lösen, Bodenklasse 3-5 (Verbreiterung/Stützstreifen)", "m3"),
    L("L_PLANUM", "Planum herstellen", "m2"),
    L("L_BODEN_VERDICHTEN", "Boden verdichten, Einschnitte", "m2"),
    L("L_FSS", "Frostschutzschicht herstellen", "m3"),
    L("L_ASPHALTTRAGSCHICHT", "Asphalttragschicht herstellen", "t", "223113113991009"),
    L("L_NAHT", "Naht in Asphaltschicht herstellen", "m", "223113907310107"),
    # --- 01.04 Unterlage reinigen + Asphalteinbau ---
    L("L_REINIGEN", "Unterlage reinigen, Asphaltbefestigung", "m2", "2231130581021"),
    L("L_ANSPRITZEN", "Bitumenemulsion aufsprühen", "m2", "223113063120999"),
    L("L_ASPHALTEINLAGE", "Asphalteinlage liefern und verlegen (Gitter mit Vliesstoff, FGSV AP 770)", "m2"),
    L("L_ASPHALTBINDER", "Asphaltbinderschicht herstellen", "m2", "22311321999901002"),
    L("L_ASPHALTDECK", "Asphaltdeckschicht herstellen", "m2", "22311332899900502"),
    L("L_ABSTUMPFUNG", "Abstumpfungsmaßnahme LFK 1/3 maschinell durchführen", "m2", "2231139521111"),
    L("L_KEHREN_VSM", "Verkehrsfläche kehren (selbstaufn. Kehrmaschine, VSM)", "m2", "22311397791"),
    L("L_NAHT_AUFWEITEN", "Naht/Anschluss zur Fuge aufweiten und säubern (schneiden)", "m", "223113937213101"),
    L("L_FUGENFUELLUNG_N2", "Fugenfüllung Querfuge herstellen (Fugenmasse N2)", "m", "22311394221131001"),
    # --- distinct ops kept separate (own recipe / function) ---
    L("L_FEINFRAESEN", "Asphalt feinfräsen (Präzisionsfräsung, Oberfläche)", "m2", "22311300599909010"),
    L("L_ASPHALT_HAND", "Asphaltschicht im Handeinbau herstellen (Kleinflächen)", "m2", "223113219999010"),
    L("L_GUSSASPHALT_DECK", "Gussasphaltdeckschicht herstellen", "m2", "22311334899900502"),
    L("L_STS", "Schottertragschicht herstellen", "m3", "223113029910"),
    L("L_DSK", "Dünnschichtbelag im Kalteinbau herstellen", "m2", "2231133899901"),
    L("L_RANDABDICHTUNG", "Randabdichtung/Nahtabdichtung herstellen (Fugenband/Randmasse)", "m", "223113942290"),
]}
