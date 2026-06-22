"""
leistungen.py — the Leistung catalog (leaf service descriptions).

A Leistung is the service itself, STLB-style: a code/STLB-Nr, a description, an
Einheit — and nothing more. It does NOT reference a Bauverfahren; the calculator
selects one at calc time. Several Leistungen may be fulfilled by the same
Bauverfahren (e.g. the three fräsen depths all use the Kaltfräse recipe; the depth
is a context value). Multiple Positionen may instantiate one Leistung at different
mengen. Exports LEISTUNGEN.
"""

from model import Leistung


def L(code, name, einheit, stlb=None):
    return Leistung(code=code, name=name, einheit=einheit, standard_kennung=stlb)


LEISTUNGEN: dict[str, Leistung] = {l.code: l for l in [
    # --- 01.00 Erdbau / Bankett ---
    L("L_BANKETT_ABTRAGEN", "Bankett abtragen und schälen", "m3"),
    L("L_BODEN_EINBAU_GROBK", "Grobkörnigen Boden liefern und einbauen", "m3"),
    L("L_BANKETTBEF_B2", "Bankettbefestigung B2 0/32 herstellen", "m3"),
    L("L_OBERBODEN", "Oberboden liefern und andecken", "m3"),
    # --- 01.01 Erschwernisse ---
    L("L_ERSCHWERNIS_FRAESEN", "Erschwernis Einfassungen (Fräsen/Aufnehmen)", "m", "2231130839503"),
    L("L_ERSCHWERNIS_ASPHALT", "Erschwernis Einfassungen (Asphaltschichten)", "m", "2231130839503"),
    # --- 01.02 Markierung / Asphalt trennen + fräsen ---
    L("L_MARK_FARBE", "Längsmarkierung entfernen, Farbe", "m", "22113100511111001"),
    L("L_MARK_PLASTIK", "Längsmarkierung entfernen, Plastik", "m", "22113100531311001"),
    L("L_TRENNEN_QUER_DECK", "Asphaltbefestigung trennen quer (Deckschicht 3-4,5 cm)", "m", "2231130382109"),
    L("L_TRENNEN_QUER_BINDER", "Asphaltbefestigung trennen quer (Binder/Trag 5-9 cm)", "m", "2231130382109"),
    L("L_FRAESEN_1_25", "Asphalt fräsen, Tiefe 1-2,5 cm", "m2", "22311300590201010"),
    L("L_FRAESEN_3_45", "Asphalt fräsen, Tiefe 3-4,5 cm", "m2", "22311300510909010"),
    L("L_FRAESEN_5_9", "Asphalt fräsen, Tiefe 5-9 cm", "m2", "22311300590909010"),
    L("L_NACHFRAESEN", "Asphalt nachfräsen, Schollenbildung 1-3 cm", "m2"),
    L("L_TRENNEN_LAENGS", "Asphaltbefestigung trennen längs (8-12 cm)", "m", "2231130381109"),
    L("L_AUFBRECHEN", "Asphaltbefestigung aufnehmen, Randstreifen m. SoB", "m2", "22311302831909003"),
    # --- 01.03 Verbreiterungs-/Stützstreifen ---
    L("L_BODEN_LOESEN", "Boden lösen, Bodenklasse 3-5 (Verbreiterung/Stützstreifen)", "m3"),
    L("L_PLANUM", "Planum herstellen (Abweichung +-2 cm, Ev2=45 MPa)", "m2"),
    L("L_BODEN_VERDICHTEN", "Boden verdichten, Einschnitte", "m2"),
    L("L_FSS_EV45", "Frostschutzschicht 0/32 herstellen (Ev2=45 MPa)", "m3"),
    L("L_ASPHALTTRAGSCHICHT", "Asphalttragschicht AC 32 T S herstellen", "t", "223113113991009"),
    L("L_NAHT", "Naht in Asphaltschicht herstellen (PmB, Längsnaht)", "m", "223113907310107"),
    L("L_FSS_EV100", "Frostschutzschicht 0/32 herstellen (Ev2=100 MPa)", "m3"),
]}