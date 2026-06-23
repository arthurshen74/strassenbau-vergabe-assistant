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
    L("L_PLANUM_VERDICHTET", "Planum herstellen und verdichten (kombiniert)", "m2"),
    L("L_BODEN_VERDICHTEN", "Boden verdichten, Einschnitte", "m2"),
    L("L_FSS_EV45", "Frostschutzschicht 0/32 herstellen (Ev2=45 MPa)", "m3"),
    L("L_ASPHALTTRAGSCHICHT", "Asphalttragschicht AC 32 T S herstellen", "t", "223113113991009"),
    L("L_NAHT", "Naht in Asphaltschicht herstellen (PmB, Längsnaht)", "m", "223113907310107"),
    L("L_FSS_EV100", "Frostschutzschicht 0/32 herstellen (Ev2=100 MPa)", "m3"),
    # --- 01.04 Unterlage reinigen (vor Asphalteinbau) ---
    L("L_REINIGEN_KEHREN", "Unterlage reinigen, Asphaltbefestigung (Einzelflächen, Kehrmaschine)", "m2", "2231130581021"),
    L("L_REINIGEN_HD", "Unterlage reinigen, Asphaltbefestigung (Hochdruck-Wasch-Saug)", "m2", "2231130581119"),
    L("L_ANSPRITZEN_GRID", "Bitumenemulsion aufsprühen, Bk100–Bk3,2 (Bettung Asphalteinlage)", "m2", "223113063120999"),
    L("L_ANSPRITZEN_VERBUND_FRAES", "Bitumenemulsion aufsprühen, Bk1,8–Bk0,3, gefräst/Pflaster (Rampenspritzgerät)", "m2", "223113063291199"),
    L("L_ANSPRITZEN_VERBUND_FRISCH", "Bitumenemulsion aufsprühen, Bk1,8–Bk0,3, Asphalt frisch (Rampenspritzgerät)", "m2", "223113063211194"),
    L("L_ASPHALTEINLAGE", "Asphalteinlage liefern und verlegen (Gitter mit Vliesstoff, FGSV AP 770)", "m2"),
    L("L_ASPHALT_TRAGSCHICHT_AC22", "Asphalttragschicht AC 22 T S herstellen (Profilausgleich, Beschicker)", "t", "223113123991001"),
    L("L_ASPHALT_BINDER_AC16", "Asphaltbinderschicht AC 16 B S herstellen (Kompaktasphalt, untere Schicht)", "m2", "22311321999901002"),
    L("L_ASPHALT_DECK_AC8", "Asphaltdeckschicht AC 8 D S herstellen (Kompaktasphalt, obere Schicht)", "m2", "22311332899900502"),
    L("L_ABSTUMPFUNG", "Abstumpfungsmaßnahme LFK 1/3 maschinell durchführen", "m2", "2231139521111"),
    L("L_KEHREN_VSM", "Verkehrsfläche kehren (selbstaufn. Kehrmaschine, VSM)", "m2", "22311397791"),
    L("L_NAHT_QUER_PMB", "Naht in Asphaltschicht herstellen (Quernaht, PmB heiß)", "m", "223113907920199"),
    L("L_NAHT_AUFWEITEN", "Naht/Anschluss zur Fuge aufweiten und säubern (schneiden)", "m", "223113937213101"),
    L("L_FUGENFUELLUNG_N2", "Fugenfüllung Querfuge herstellen (Fugenmasse N2)", "m", "22311394221131001"),
]}