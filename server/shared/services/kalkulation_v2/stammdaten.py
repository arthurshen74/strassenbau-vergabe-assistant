"""
stammdaten.py — Kostenstammdaten: the rate book.

Org-global KONSTANTE rates (fuel, wages, machine rates, disposal, fixed outputs)
plus the two STAMMDATEN bridge variables that pull physical properties from the
material catalog. These are reference data — slow-moving, editable in the UI,
the same for every bid. Exports STAMMDATEN_VARIABLEN (variable name -> definition).
"""

from shared.services.kalkulation_v2.model import (
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
konst("entsorgung_fraesasphalt_eur_pro_t", "5.00", "€/t")  # superseded by class formula (kept for back-compat)
# Fräsgut disposal/recycling by Belastungsklasse (PLACEHOLDERS — set from Schadstoffgutachten):
konst("ent_fraesgut_verwertbar", "0.00", "€/t", "1 verwertbar/unbelastet (oft Gutschrift, hier 0)")
konst("ent_fraesgut_belastet", "25.00", "€/t", "2 belastet, nicht teerhaltig")
konst("ent_fraesgut_pechhaltig", "110.00", "€/t", "3 pechhaltig/teerhaltig (PAK) – Sonderabfall")
konst("entsorgung_boden_z2_eur_pro_t", "16.00", "€/t")
konst("erschwernis_zulage_eur_pro_m", "8.50", "€/m")
konst("entsorgung_demark_eur_pro_m", "0.15", "€/m", "Abfall Demarkierung aufnehmen+verwerten (Platzhalter)")
konst("asphalt_preis_eur_pro_t", "72.00", "€/t", "Asphaltmischgut AC 32 T S")
konst("pmb_preis_eur_pro_t", "850.00", "€/t", "Polymermod. Bitumen")
konst("naht_material_g_pro_m_cm", "50", "g/(m·cm)")
# naht_dicke_cm is now per-position (LANGTEXT) — see kontext_variablen.py

# --- fixed machine outputs (depth-independent) ---
konst("einbau_leistung_m3_pro_h", "35", "m³/h")
konst("bagger_leistung_m3_pro_h", "45", "m³/h")
konst("planum_leistung_m2_pro_h", "250", "m²/h")
konst("walze_leistung_m2_pro_h", "400", "m²/h")
konst("asphalt_einbau_leistung_t_pro_h", "90", "t/h", "Fertiger + Beschicker + Walzen (maschinell)")
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

# --- Bankettbefestigung: narrow-strip productivity + dedicated gear (PLACEHOLDERS) ---
# Same machines as FSS for lay/profile (same €/h) but slower on a ~1,0 m strip:
konst("bankett_legen_leistung_m3_pro_h", "25", "m³/h", "Liefer-/Legeleistung Radlader (Bankett)")
konst("bankett_profil_leistung_m2_pro_h", "300", "m²/h", "Profilierleistung Grader (Bankett, je Lage)")
# Compaction: kleine Tandemwalze (reuses the Ev2->Übergänge curve, lower output/Übergang):
konst("bankettwalze_stundensatz_eur", "45", "€/h", "kleine Tandemwalze inkl. Verschleiß")
konst("bankettwalze_l_pro_h", "6", "l/h")
konst("bankettwalze_uebergang_leistung_m2_pro_h", "700", "m²/(h·Übergang)", "Walzleistung Bankett je Übergang")
# Bankettfertiger (lay + level to Quergefälle in one pass):
konst("bankettfertiger_stundensatz_eur", "120", "€/h", "Bankettfertiger inkl. Verschleiß")
konst("bankettfertiger_l_pro_h", "14", "l/h")
konst("bankettfertiger_leistung_m2_pro_h", "350", "m²/h", "Einbau+Abziehen Bankettfertiger")

# --- Grobkörniger Boden (Auffüllung unter Banketten, Einzelflächen) — PLACEHOLDERS ---
# LV nennt KEIN Ev2/DPr -> fester Übergangs-Ansatz (Standardverdichtung), nicht Ev2-getrieben.
# Einzelflächen -> niedrige Produktivität.
konst("boden_legen_leistung_m3_pro_h", "30", "m³/h", "Liefer-/Einbauleistung Radlader (Einzelflächen)")
konst("boden_profil_leistung_m2_pro_h", "250", "m²/h", "Profil/Planum Grader (einbegriffen)")
konst("boden_verdicht_uebergaenge", "4", "-", "Walzübergänge (fester Ansatz, kein Ev2 im LV)")
konst("boden_verdicht_leistung_m2_pro_h_uebergang", "800", "m²/(h·Übergang)", "Walzleistung Boden je Übergang")

# --- Oberboden andecken (Bankettbereich, dünn ≤5 cm, KEINE Verdichtung) — PLACEHOLDERS ---
konst("oberboden_andeck_hand_m2_pro_h", "80", "m²/h", "Andeckleistung Kolonne (Hand)")
konst("oberboden_andeck_grader_m2_pro_h", "400", "m²/h", "Andeckleistung Grader")

# --- Unterlage reinigen: sweeper vs high-pressure wash-vacuum (PLACEHOLDERS) ---
konst("kehr_leistung_m2_pro_h", "1200", "m²/h", "selbstaufn. Kehrmaschine, Einzelflächen")
konst("kehrmaschine_stundensatz_eur", "60", "€/h"); konst("kehrmaschine_l_pro_h", "8", "l/h")
konst("ent_kehrgut_eur_pro_m2", "0.05", "€/m²", "Kehrgut verwerten (leichtes Kehrgut)")
konst("hd_reinigung_leistung_m2_pro_h", "1500", "m²/h", "HD-Wasch-Sauganlage, 0–6 km/h × 2,30 m")
konst("hd_waschsaug_stundensatz_eur", "320", "€/h", "HD-Wasch-Sauganlage inkl. Wasser/Verschleiß")
konst("hd_waschsaug_l_pro_h", "40", "l/h")
konst("ent_waschschlamm_eur_pro_m2", "0.25", "€/m²", "Waschschlamm verwerten (Platzhalter; s. Belastung)")

# --- Anspritzen / Schichtenverbund (Rampenspritzgerät) — PLACEHOLDERS ---
konst("anspritz_leistung_m2_pro_h", "4000", "m²/h", "Spritzleistung Rampenspritzgerät")
konst("spritzgeraet_stundensatz_eur", "90", "€/h"); konst("spritzgeraet_l_pro_h", "10", "l/h")

# --- Asphalt paving train + supporting works (PLACEHOLDERS) ---
konst("asphalt_zug_geraet_eur_pro_h", "520", "€/h", "Fertiger+Beschicker+2 Walzen inkl. Verschleiß/Kraftstoff")
konst("asphalt_kolonne", "6", "Pers.", "Einbaukolonne")
konst("grid_verlege_leistung_m2_pro_h", "400", "m²/h", "Asphalteinlage verlegen (Fachpersonal)")
konst("grid_geraet_stundensatz_eur", "40", "€/h"); konst("grid_kolonne", "4", "Pers.")
konst("abstreukoernung_preis_eur_pro_t", "30", "€/t", "Abstreukörnung LFK 1/3")
konst("abstreuen_leistung_m2_pro_h", "3000", "m²/h", "maschinell abstreuen + einwalzen")
konst("abstreuer_stundensatz_eur", "75", "€/h"); konst("abstreuer_l_pro_h", "9", "l/h")
konst("ent_abstreu_eur_pro_m2", "0.05", "€/m²", "loses Abstreugut aufnehmen+verwerten")
konst("naht_aufweiten_leistung_m_pro_h", "60", "m/h", "Fuge schneiden/aufweiten 25×10 mm")
konst("fugenmasse_preis_eur_pro_t", "1800", "€/t", "heiß verarbeitbare Fugenmasse N2 + Voranstrich")
konst("fugenmasse_dichte_t_pro_m3", "1.10", "t/m³")
konst("fugenfuellung_leistung_m_pro_h", "80", "m/h")
konst("fugen_geraet_stundensatz_eur", "30", "€/h"); konst("fugen_geraet_l_pro_h", "3", "l/h")

# --- Asphalt-Handeinbau (Kleinflächen): langsame Kolonne + kleine Walze (PLACEHOLDERS) ---
konst("handeinbau_leistung_m2_pro_h", "40", "m²/h", "Einbauleistung Handkolonne (Kleinflächen)")
konst("handeinbau_kolonne", "5", "Pers.", "Einbaukolonne Handeinbau")

# --- Gussasphalt (MA, fließfähig, KEINE Verdichtung; Abstreuen separat) — PLACEHOLDERS ---
konst("gussasphalt_preis_eur_pro_t", "120.00", "€/t", "Gussasphaltmischgut MA 8/11 S")
konst("gussasphalt_leistung_m2_pro_h", "80", "m²/h", "Einbauleistung Gussasphalt (Bohle/Kübel)")
konst("gussasphalt_geraet_stundensatz_eur", "150", "€/h", "Gussasphaltfertiger/Kocher inkl. Verschleiß")
konst("gussasphalt_l_pro_h", "15", "l/h")
konst("gussasphalt_kolonne", "5", "Pers.", "Einbaukolonne Gussasphalt")

# --- DSK (Dünnschichtbelag im Kalteinbau / Slurry): Material je m², schnelle Maschine — PLACEHOLDERS ---
konst("dsk_material_eur_pro_m2", "4.50", "€/m²", "DSK-Mischgut (Emulsion + Splitt) je m²")
konst("dsk_leistung_m2_pro_h", "2000", "m²/h", "Einbauleistung DSK-/Slurry-Fertiger")
konst("dsk_geraet_stundensatz_eur", "180", "€/h", "DSK-Fertiger inkl. Verschleiß")
konst("dsk_l_pro_h", "20", "l/h")
konst("dsk_kolonne", "4", "Pers.", "Einbaukolonne DSK")

# --- Randabdichtung/Nahtabdichtung: Dichtband/-masse je m, kleine Kolonne + Gerät — PLACEHOLDERS ---
konst("randabdichtung_material_eur_pro_m", "3.00", "€/m", "Fugenband/Randmasse je m")
konst("randabdichtung_leistung_m_pro_h", "60", "m/h", "Abdichtleistung (Reinigen + Anbringen)")
konst("randabdichtung_geraet_stundensatz_eur", "20", "€/h", "Applikator/Heizgerät")
konst("randabdichtung_l_pro_h", "2", "l/h")

# --- master-data bridges (pull from the chosen Baustoff) ---
stammdaten("dichte_t_pro_m3", "baustoff.rohdichte_t_pro_m3", "t/m³", "Rohdichte Baustoff")
stammdaten("verdichtungsfaktor", "baustoff.verdichtungsfaktor", "-", "Verdichtungsfaktor")