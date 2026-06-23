"""
stammdaten.py — Kostenstammdaten: the rate book.

Org-global KONSTANTE rates (fuel, wages, machine rates, disposal, fixed outputs)
plus the two STAMMDATEN bridge variables that pull physical properties from the
material catalog. These are reference data — slow-moving, editable in the UI,
the same for every bid. Exports STAMMDATEN_VARIABLEN (variable name -> definition).
"""

from model import (
    AufloesungsMethode as M, AufloesungsSchritt as Schritt, D, VariableDefinition as VarDef,
)

STAMMDATEN_VARIABLEN: dict[str, VarDef] = {}


def konst(name, wert, einheit, bez=None):
    STAMMDATEN_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez or name, einheit=einheit,
                                        aufloesung=[Schritt(methode=M.KONSTANTE, konstante=D(wert))])


def stammdaten(name, pfad, einheit, bez=None):
    STAMMDATEN_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez or name, einheit=einheit,
                                        aufloesung=[Schritt(methode=M.STAMMDATEN, stammdaten_pfad=pfad)])


# --- global rates ---
konst("kraftstoffpreis_eur_pro_l", "1.75", "€/l", "Kraftstoffpreis")
konst("stundenlohn_eur", "42.00", "€/h", "Stundenlohn")
konst("transport_eur_pro_t_km", "0.12", "€/(t·km)", "Transportsatz")

# --- machine rates (incl. Verschleiß) ---
konst("bagger_stundensatz_eur", "110", "€/h"); konst("bagger_l_pro_h", "17", "l/h")
konst("radlader_stundensatz_eur", "70", "€/h"); konst("radlader_l_pro_h", "14", "l/h")
konst("walze_stundensatz_eur", "50", "€/h"); konst("walze_l_pro_h", "9", "l/h")
konst("kaltfraese_stundensatz_eur", "210", "€/h"); konst("kaltfraese_l_pro_h", "60", "l/h")
konst("schneider_stundensatz_eur", "42", "€/h"); konst("schneider_l_pro_h", "4", "l/h")
konst("markfraese_stundensatz_eur", "60", "€/h"); konst("markfraese_l_pro_h", "6", "l/h")
konst("aufbruch_stundensatz_eur", "130", "€/h"); konst("aufbruch_l_pro_h", "20", "l/h")
konst("grader_stundensatz_eur", "95", "€/h"); konst("grader_l_pro_h", "14", "l/h")
konst("naht_geraet_stundensatz_eur", "25", "€/h"); konst("naht_geraet_l_pro_h", "3", "l/h")

# --- material / disposal rates ---
konst("dichte_asphalt_t_pro_m3", "2.40", "t/m³", "Rohdichte Asphalt")
konst("entsorgung_fraesasphalt_eur_pro_t", "5.00", "€/t")
konst("entsorgung_boden_z2_eur_pro_t", "16.00", "€/t")
konst("erschwernis_zulage_eur_pro_m", "8.50", "€/m")
konst("asphalt_preis_eur_pro_t", "72.00", "€/t", "Asphaltmischgut AC 32 T S")
konst("pmb_preis_eur_pro_t", "850.00", "€/t", "Polymermod. Bitumen")
konst("naht_material_g_pro_m_cm", "50", "g/(m·cm)")
konst("naht_dicke_cm", "16", "cm")

# --- fixed machine outputs (depth-independent) ---
konst("einbau_leistung_m3_pro_h", "35", "m³/h")
konst("bagger_leistung_m3_pro_h", "45", "m³/h")
konst("planum_leistung_m2_pro_h", "250", "m²/h")
konst("walze_leistung_m2_pro_h", "400", "m²/h")
konst("asphalt_einbau_leistung_t_pro_h", "18", "t/h", "Handeinbau 2-lagig")
konst("naht_leistung_m_pro_h", "150", "m/h")

# --- FSS decomposition: lay / profile / compact rates (PLACEHOLDERS – set in rate book) ---
konst("radlader_leistung_m3_pro_h", "40", "m³/h", "Liefer-/Legeleistung Radlader (FSS)")
konst("profil_leistung_m2_pro_h", "500", "m²/h", "Profilierleistung Grader (je Lage)")
konst("walze_uebergang_leistung_m2_pro_h", "1200", "m²/(h·Übergang)", "Walzleistung je Übergang")
konst("fertiger_stundensatz_eur", "180", "€/h", "Fertiger inkl. Verschleiß")
konst("fertiger_l_pro_h", "25", "l/h")
konst("fertiger_leistung_m2_pro_h", "600", "m²/h", "Einbau+Abziehen Fertiger (ein Zug)")
konst("max_lagendicke_b2_m", "0.30", "m", "max. verdichtete Lagendicke B2 0/32")
# Ev2 target -> Walzübergänge: linear zwischen zwei Ankern, dann aufgerundet
konst("verdicht_uebergaenge_ev45", "3", "-", "Übergänge @ Ev2=45")
konst("verdicht_uebergaenge_ev100", "6", "-", "Übergänge @ Ev2=100")
konst("ev2_anker_min", "45", "MPa"); konst("ev2_anker_max", "100", "MPa")

# --- master-data bridges (pull from the chosen Baustoff) ---
stammdaten("dichte_t_pro_m3", "baustoff.rohdichte_t_pro_m3", "t/m³", "Rohdichte Baustoff")
stammdaten("verdichtungsfaktor", "baustoff.verdichtungsfaktor", "-", "Verdichtungsfaktor")