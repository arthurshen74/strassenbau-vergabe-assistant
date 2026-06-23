"""
positionen.py — the LV-Positionen (instance layer).

A Position references a Leistung (the service) plus the per-bid menge and extracted
context. It does NOT pin a Bauverfahren by default — the calculator selects one from
the Leistung's candidates (see leistung_bauverfahren.py). bauverfahren_key is an
OPTIONAL override: set it only to force a specific recipe (must be a valid candidate).
Kurztext and Einheit are inherited from the Leistung. Multiple Positionen may point at
one Leistung (different menge). Exports Position and POSITIONEN.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from model import D


class Position(BaseModel):
    oz: str
    leistung_key: str                       # -> LEISTUNGEN (what)
    menge: Decimal
    bauverfahren_key: str | None = None     # optional override of the selected recipe
    baustoff_code: str | None = None
    kontext: dict[str, Decimal] = Field(default_factory=dict)


def P(oz, leistung, menge, baustoff=None, bauverfahren=None, **kontext):
    return Position(oz=oz, leistung_key=leistung, menge=D(menge),
                    bauverfahren_key=bauverfahren, baustoff_code=baustoff,
                    kontext={k: D(v) for k, v in kontext.items()})


POSITIONEN: list[Position] = [
    P("01.00.0002", "L_BANKETT_ABTRAGEN", "500", baustoff="GROBK_BODEN", entfernung_km="18", anzahl_arbeiter="3"),
    P("01.00.0003", "L_BODEN_EINBAU_GROBK", "100", baustoff="GROBK_BODEN", materialpreis_eur_pro_t="9.50", entfernung_km="14", schichtdicke_m="0.30"),
    P("01.00.0004", "L_BANKETTBEF_B2", "570", baustoff="MG_B2_0_32", materialpreis_eur_pro_t="19.00", entfernung_km="14", anzahl_arbeiter="3", schichtdicke_m="0.20", ev2_ziel="70"),
    P("01.00.0005", "L_OBERBODEN", "120", baustoff="OBERBODEN", materialpreis_eur_pro_t="7.00", entfernung_km="8", schichtdicke_m="0.05", anzahl_arbeiter="3"),
    P("01.00.0008", "L_OBERBODEN", "230", baustoff="OBERBODEN", materialpreis_eur_pro_t="7.00", entfernung_km="8", schichtdicke_m="0.125", anzahl_arbeiter="3", erschwernisfaktor="1.4", bauverfahren="BV_OBERBODEN_HAND"),
    P("01.01.0001", "L_ERSCHWERNIS_FRAESEN", "40"),
    P("01.01.0002", "L_ERSCHWERNIS_ASPHALT", "40"),
    P("01.02.0001", "L_MARK_FARBE", "2850", markierung_leistung_m_pro_h="100"),
    P("01.02.0002", "L_MARK_PLASTIK", "475", markierung_leistung_m_pro_h="90"),
    P("01.02.0003", "L_TRENNEN_QUER_DECK", "15", tiefe_cm="4"),
    P("01.02.0004", "L_TRENNEN_QUER_BINDER", "15", tiefe_cm="7"),
    P("01.02.0005", "L_FRAESEN_1_25", "400", tiefe_cm="2", erschwernisfaktor="3.0", fraesgut_klasse="1"),
    P("01.02.0006", "L_FRAESEN_3_45", "7800", tiefe_cm="4", fraesgut_klasse="1"),
    P("01.02.0007", "L_FRAESEN_5_9", "7800", tiefe_cm="7", fraesgut_klasse="1"),
    P("01.02.0008", "L_NACHFRAESEN", "4700", tiefe_cm="2", erschwernisfaktor="1.6", fraesgut_klasse="1"),
    P("01.02.0009", "L_TRENNEN_LAENGS", "1500", tiefe_cm="10"),
    P("01.02.0010", "L_AUFBRECHEN", "450", tiefe_cm="10", fraesgut_klasse="1"),
    # --- 01.03 Verbreiterungs-/Stützstreifen ---
    P("01.03.0001", "L_BODEN_LOESEN", "200", baustoff="BODEN_KL_3_5", entfernung_km="16", anzahl_arbeiter="3"),
    P("01.03.0002", "L_PLANUM", "950"),
    P("01.03.0003", "L_BODEN_VERDICHTEN", "950"),
    P("01.03.0004", "L_FSS_EV45", "100", baustoff="MG_B2_0_32", materialpreis_eur_pro_t="19.00", entfernung_km="14", schichtdicke_m="0.40", ev2_ziel="45"),
    P("01.03.0005", "L_ASPHALTTRAGSCHICHT", "400", entfernung_km="30", anzahl_arbeiter="4"),
    P("01.03.0006", "L_NAHT", "1500", naht_dicke_cm="16"),
    P("01.03.0007", "L_BODEN_LOESEN", "60", baustoff="BODEN_KL_3_5", entfernung_km="16"),
    P("01.03.0008", "L_PLANUM", "300"),
    P("01.03.0009", "L_BODEN_VERDICHTEN", "300"),
    P("01.03.0010", "L_FSS_EV100", "60", baustoff="MG_B2_0_32", materialpreis_eur_pro_t="19.00", entfernung_km="14", schichtdicke_m="0.40", ev2_ziel="100"),
    # --- 01.04 Unterlage reinigen ---
    P("01.04.0001", "L_REINIGEN_KEHREN", "7800"),
    P("01.04.0002", "L_REINIGEN_HD", "7800"),
    P("01.04.0003", "L_ANSPRITZEN_GRID", "1450", bindemittelmenge_kg_pro_m2="2.0", materialpreis_eur_pro_t="700"),
    P("01.04.0005", "L_ANSPRITZEN_VERBUND_FRAES", "7800", bindemittelmenge_kg_pro_m2="0.30", materialpreis_eur_pro_t="600"),
    P("01.04.0007", "L_ANSPRITZEN_VERBUND_FRISCH", "7800", bindemittelmenge_kg_pro_m2="0.30", materialpreis_eur_pro_t="600"),
    P("01.04.0004", "L_ASPHALTEINLAGE", "1450", grid_preis_eur_pro_m2="6.50"),
    P("01.04.0006", "L_ASPHALT_TRAGSCHICHT_AC22", "1900", asphalt_preis_eur_pro_t="75", entfernung_km="30"),
    P("01.04.0008", "L_ASPHALT_BINDER_AC16", "7800", einbaudicke_cm="7.5", asphalt_preis_eur_pro_t="82", entfernung_km="30"),
    P("01.04.0009", "L_ASPHALT_DECK_AC8", "7800", einbaudicke_cm="2.5", asphalt_preis_eur_pro_t="95", entfernung_km="30"),
    P("01.04.0010", "L_ABSTUMPFUNG", "7800", abstreumenge_kg_pro_m2="1.0"),
    P("01.04.0011", "L_KEHREN_VSM", "7800"),
    P("01.04.0012", "L_NAHT_QUER_PMB", "20", naht_dicke_cm="10"),
    P("01.04.0013", "L_NAHT_AUFWEITEN", "20"),
    P("01.04.0014", "L_FUGENFUELLUNG_N2", "20", fugenspalttiefe_mm="25", fugenspaltbreite_mm="10"),
]