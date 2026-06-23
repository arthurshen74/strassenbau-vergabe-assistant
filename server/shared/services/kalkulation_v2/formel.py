"""
formel.py — the calculation formulas (the editable DSL expressions).

Each formula produces one variable; registering it also creates that variable's
definition (resolution method = FORMEL). Formulas reference variables from
stammdaten (rates), kontext_variablen (geometry, extracted inputs) and each other;
the Kalkulator resolves the dependency graph lazily at calc time.

Exports FORMELN (name -> Formel) and FORMEL_VARIABLEN (name -> VariableDefinition).
"""

from model import (
    AufloesungsMethode as M, AufloesungsSchritt as Schritt, Formel, VariableDefinition as VarDef,
)

FORMELN: dict[str, Formel] = {}
FORMEL_VARIABLEN: dict[str, VarDef] = {}


def formel(name, ausdruck, einheit, bez=None):
    FORMELN[name] = Formel(name=name, ergebnis_variable=name, ausdruck=ausdruck, einheit=einheit)
    FORMEL_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez or name, einheit=einheit,
                                    aufloesung=[Schritt(methode=M.FORMEL, formel_name=name)])


# --- machine outputs (depth-dependent) ---
formel("fraese_leistung_m2_pro_h", "max(120, 1000 / tiefe_cm) / erschwernisfaktor", "m²/h")
formel("schnitt_leistung_m_pro_h", "max(18, 220 / tiefe_cm)", "m/h")
formel("aufbruch_leistung_m2_pro_h", "max(30, 500 / tiefe_cm)", "m²/h")

# --- operating hours (shared between machine-cost and labour) ---
formel("fraese_stunden", "flaeche_m2 / fraese_leistung_m2_pro_h", "h")
formel("schnitt_stunden", "laenge_m / schnitt_leistung_m_pro_h", "h")
formel("einbau_stunden", "volumen_m3 / einbau_leistung_m3_pro_h", "h")
formel("bagger_stunden", "volumen_m3 / bagger_leistung_m3_pro_h", "h")
formel("aufbruch_stunden", "flaeche_m2 / aufbruch_leistung_m2_pro_h", "h")
formel("markierung_stunden", "laenge_m / markierung_leistung_m_pro_h", "h")
formel("planum_stunden", "flaeche_m2 / planum_leistung_m2_pro_h", "h")
formel("verdichten_stunden", "flaeche_m2 / walze_leistung_m2_pro_h", "h")
formel("asphalt_stunden", "menge_t / asphalt_einbau_leistung_t_pro_h", "h")
formel("naht_stunden", "laenge_m / naht_leistung_m_pro_h", "h")

# --- tonnages ---
formel("tonnage_material", "volumen_m3 * dichte_t_pro_m3 * verdichtungsfaktor", "t")
formel("tonnage_abtrag", "volumen_m3 * dichte_t_pro_m3", "t")
formel("tonnage_fraesgut", "flaeche_m2 * (tiefe_cm / 100) * dichte_asphalt_t_pro_m3", "t")
formel("tonnage_aufbruch", "flaeche_m2 * (tiefe_cm / 100) * dichte_asphalt_t_pro_m3", "t")
formel("naht_menge_t", "naht_material_g_pro_m_cm * naht_dicke_cm * laenge_m / 1000000", "t")

# --- material cost lines ---
formel("materialkosten", "tonnage_material * materialpreis_eur_pro_t", "€")
formel("materialkosten_asphalt", "menge_t * asphalt_preis_eur_pro_t", "€")
formel("materialkosten_naht", "naht_menge_t * pmb_preis_eur_pro_t", "€")

# --- machine cost lines ---
formel("mk_einbau", "einbau_stunden * (radlader_stundensatz_eur + walze_stundensatz_eur "
                    "+ (radlader_l_pro_h + walze_l_pro_h) * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_bagger", "bagger_stunden * (bagger_stundensatz_eur + bagger_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_fraese", "fraese_stunden * (kaltfraese_stundensatz_eur + kaltfraese_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_schnitt", "schnitt_stunden * (schneider_stundensatz_eur + schneider_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_markierung", "markierung_stunden * (markfraese_stundensatz_eur + markfraese_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_aufbruch", "aufbruch_stunden * (aufbruch_stundensatz_eur + aufbruch_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_planum", "planum_stunden * ((grader_stundensatz_eur + grader_l_pro_h * kraftstoffpreis_eur_pro_l) "
                    "+ (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l))", "€")
formel("mk_verdichten", "verdichten_stunden * (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_asphalt", "asphalt_stunden * asphalt_zug_geraet_eur_pro_h", "€")
formel("mk_naht", "naht_stunden * (naht_geraet_stundensatz_eur + naht_geraet_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")

# --- labour cost lines ---
formel("lohn_einbau", "einbau_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_bagger", "bagger_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_fraese", "fraese_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_schnitt", "schnitt_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_markierung", "markierung_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_aufbruch", "aufbruch_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_planum", "planum_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_verdichten", "verdichten_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_asphalt", "asphalt_stunden * stundenlohn_eur * asphalt_kolonne", "€")
formel("lohn_naht", "naht_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_erschwernis", "laenge_m * erschwernis_zulage_eur_pro_m", "€")

# --- disposal cost lines ---
formel("ent_boden", "tonnage_abtrag * entsorgung_boden_z2_eur_pro_t", "€")
formel("ent_demark", "laenge_m * entsorgung_demark_eur_pro_m", "€")
formel("ent_fraesgut", "tonnage_fraesgut * entsorgung_fraesasphalt_eur_pro_t", "€")
# Disposal rate keyed by Belastungsklasse (1 verwertbar / 2 belastet / 3 pechhaltig):
formel("entsorgung_fraesasphalt_eur_pro_t",
       "ent_fraesgut_verwertbar if fraesgut_klasse <= 1 else "
       "(ent_fraesgut_belastet if fraesgut_klasse <= 2 else ent_fraesgut_pechhaltig)",
       "€/t", "Entsorgungs-/Verwertungssatz Fräsgut je Belastungsklasse")
formel("ent_aufbruch", "tonnage_aufbruch * entsorgung_fraesasphalt_eur_pro_t", "€")

# --- transport cost lines ---
formel("trans_material", "tonnage_material * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_boden", "tonnage_abtrag * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_fraesgut", "tonnage_fraesgut * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_aufbruch", "tonnage_aufbruch * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_asphalt", "menge_t * transport_eur_pro_t_km * entfernung_km", "€")


# --------------------------------------------------------------------------- #
# FSS decomposition: lay / profile / compact, all derived from the booked m³.
# Geometry bridge — area from booked volume and the (extracted) layer thickness:
formel("flaeche_m2", "volumen_m3 / schichtdicke_m", "m²", "Fläche (aus Volumen/Schichtdicke)")
# Lifts: a layer thicker than the max lift goes in several passes of lay+level+compact.
formel("anzahl_lagen", "ceil(schichtdicke_m / max_lagendicke_b2_m)", "-", "Anzahl Lagen")
# Walzübergänge as a (clamped) linear function of the Ev2 target, then rounded up.
formel("verdicht_uebergaenge",
       "ceil(verdicht_uebergaenge_ev45 + (max(ev2_anker_min, min(ev2_anker_max, ev2_ziel)) - ev2_anker_min) "
       "* (verdicht_uebergaenge_ev100 - verdicht_uebergaenge_ev45) / (ev2_anker_max - ev2_anker_min))",
       "-", "Walzübergänge aus Ev2-Ziel")

# Operating hours per step
formel("fss_legen_stunden", "volumen_m3 / radlader_leistung_m3_pro_h", "h")          # Radlader: by volume
formel("fss_profil_stunden", "flaeche_m2 * anzahl_lagen / profil_leistung_m2_pro_h", "h")  # Grader: area x lifts
formel("fss_verdicht_stunden",
       "flaeche_m2 * anzahl_lagen * verdicht_uebergaenge / walze_uebergang_leistung_m2_pro_h", "h")
formel("fss_fertiger_stunden", "flaeche_m2 / fertiger_leistung_m2_pro_h", "h")        # Fertiger: lay+level, area

# Machine cost lines (rate incl. Verschleiß + fuel)
formel("mk_fss_legen", "fss_legen_stunden * (radlader_stundensatz_eur + radlader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_fss_profil", "fss_profil_stunden * (grader_stundensatz_eur + grader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_fss_verdicht", "fss_verdicht_stunden * (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_fss_fertiger", "fss_fertiger_stunden * (fertiger_stundensatz_eur + fertiger_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")

# Labour: laying carries the crew; solo machine steps carry one operator (PLACEHOLDER staffing)
formel("lohn_fss_legen", "fss_legen_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_fss_profil", "fss_profil_stunden * stundenlohn_eur", "€")
formel("lohn_fss_verdicht", "fss_verdicht_stunden * stundenlohn_eur", "€")
formel("lohn_fss_fertiger", "fss_fertiger_stunden * stundenlohn_eur * anzahl_arbeiter", "€")


# --------------------------------------------------------------------------- #
# Bankettbefestigung: same skeleton as FSS (m³->area bridge, lifts, Ev2->passes)
# but narrow-strip productivity and Bankett-specific gear. Material/transport and
# the anzahl_lagen / verdicht_uebergaenge / flaeche_m2 formulas are reused as-is.
formel("bankett_legen_stunden", "volumen_m3 / bankett_legen_leistung_m3_pro_h", "h")
formel("bankett_profil_stunden", "flaeche_m2 * anzahl_lagen / bankett_profil_leistung_m2_pro_h", "h")
formel("bankett_verdicht_stunden",
       "flaeche_m2 * anzahl_lagen * verdicht_uebergaenge / bankettwalze_uebergang_leistung_m2_pro_h", "h")
formel("bankett_fertiger_stunden", "flaeche_m2 / bankettfertiger_leistung_m2_pro_h", "h")

formel("mk_bankett_legen", "bankett_legen_stunden * (radlader_stundensatz_eur + radlader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_bankett_profil", "bankett_profil_stunden * (grader_stundensatz_eur + grader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_bankett_verdicht", "bankett_verdicht_stunden * (bankettwalze_stundensatz_eur + bankettwalze_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_bankett_fertiger", "bankett_fertiger_stunden * (bankettfertiger_stundensatz_eur + bankettfertiger_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")

formel("lohn_bankett_legen", "bankett_legen_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_bankett_profil", "bankett_profil_stunden * stundenlohn_eur", "€")
formel("lohn_bankett_verdicht", "bankett_verdicht_stunden * stundenlohn_eur", "€")
formel("lohn_bankett_fertiger", "bankett_fertiger_stunden * stundenlohn_eur * anzahl_arbeiter", "€")


# --------------------------------------------------------------------------- #
# Grobkörniger Boden (Auffüllung unter Banketten): liefern/legen + profilieren
# (Planum einbegriffen) + verdichten. Reuses the m³->area bridge and lifts, but
# compaction uses a FIXED Übergangszahl (boden_verdicht_uebergaenge) because the
# LV states no Ev2/DPr — NOT the Ev2-interpolated curve.
formel("boden_legen_stunden", "volumen_m3 / boden_legen_leistung_m3_pro_h", "h")
formel("boden_profil_stunden", "flaeche_m2 * anzahl_lagen / boden_profil_leistung_m2_pro_h", "h")
formel("boden_verdicht_stunden",
       "flaeche_m2 * anzahl_lagen * boden_verdicht_uebergaenge / boden_verdicht_leistung_m2_pro_h_uebergang", "h")

formel("mk_boden_legen", "boden_legen_stunden * (radlader_stundensatz_eur + radlader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_boden_profil", "boden_profil_stunden * (grader_stundensatz_eur + grader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("mk_boden_verdicht", "boden_verdicht_stunden * (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")

formel("lohn_boden_legen", "boden_legen_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_boden_profil", "boden_profil_stunden * stundenlohn_eur", "€")
formel("lohn_boden_verdicht", "boden_verdicht_stunden * stundenlohn_eur", "€")


# --------------------------------------------------------------------------- #
# Oberboden andecken: liefern + profilgerecht andecken, KEINE Verdichtung.
# Two methods (Hand-Kolonne vs Grader); area from volume / Andeckdicke (LV: bis 5 cm).
# No lifts, no passes, no Ev2 — topsoil is spread for vegetation, not compacted.
formel("oberboden_hand_stunden", "flaeche_m2 * erschwernisfaktor / oberboden_andeck_hand_m2_pro_h", "h")
formel("oberboden_grader_stunden", "flaeche_m2 / oberboden_andeck_grader_m2_pro_h", "h")
formel("lohn_oberboden_hand", "oberboden_hand_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("mk_oberboden_grader", "oberboden_grader_stunden * (grader_stundensatz_eur + grader_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_oberboden_grader", "oberboden_grader_stunden * stundenlohn_eur", "€")


# --------------------------------------------------------------------------- #
# Unterlage reinigen: area-only (machine + labour + Kehrgut/slurry). Two methods.
formel("kehr_stunden", "flaeche_m2 / kehr_leistung_m2_pro_h", "h")
formel("mk_kehren", "kehr_stunden * (kehrmaschine_stundensatz_eur + kehrmaschine_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_kehren", "kehr_stunden * stundenlohn_eur", "€")  # selbstaufnehmend: 1 Bediener
formel("ent_kehrgut", "flaeche_m2 * ent_kehrgut_eur_pro_m2", "€")

formel("hd_stunden", "flaeche_m2 / hd_reinigung_leistung_m2_pro_h", "h")
formel("mk_hd_reinigung", "hd_stunden * (hd_waschsaug_stundensatz_eur + hd_waschsaug_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_hd_reinigung", "hd_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("ent_waschschlamm", "flaeche_m2 * ent_waschschlamm_eur_pro_m2", "€")


# --------------------------------------------------------------------------- #
# Anspritzen (Schichtenverbund): binder-dominated. Material = Spritzmenge × Fläche
# × Emulsionspreis; the spray pass itself is minor. (materialpreis_eur_pro_t = €/t Emulsion.)
formel("bindemittel_menge_t", "bindemittelmenge_kg_pro_m2 * flaeche_m2 / 1000", "t")
formel("mk_bindemittel", "bindemittel_menge_t * materialpreis_eur_pro_t", "€")
formel("anspritzen_stunden", "flaeche_m2 / anspritz_leistung_m2_pro_h", "h")
formel("mk_anspritzen", "anspritzen_stunden * (spritzgeraet_stundensatz_eur + spritzgeraet_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_anspritzen", "anspritzen_stunden * stundenlohn_eur", "€")  # 1 Bediener


# --------------------------------------------------------------------------- #
# Asphalt tonnage bridge: t-billed positions book menge_t directly (resolver
# short-circuits); m²-billed courses derive it from area × thickness × density.
formel("menge_t", "flaeche_m2 * (einbaudicke_cm / 100) * dichte_asphalt_t_pro_m3", "t")

# Asphalteinlage (reinforcement grid): material per m² + specialist laying.
formel("grid_materialkosten", "flaeche_m2 * grid_preis_eur_pro_m2", "€")
formel("grid_stunden", "flaeche_m2 / grid_verlege_leistung_m2_pro_h", "h")
formel("mk_grid", "grid_stunden * grid_geraet_stundensatz_eur", "€")
formel("lohn_grid", "grid_stunden * stundenlohn_eur * grid_kolonne", "€")

# Abstumpfung (gritting): chippings + machine spread/roll + pick up loose grit.
formel("abstreu_menge_t", "abstreumenge_kg_pro_m2 * flaeche_m2 / 1000", "t")
formel("mk_abstreu_material", "abstreu_menge_t * abstreukoernung_preis_eur_pro_t", "€")
formel("abstreu_stunden", "flaeche_m2 / abstreuen_leistung_m2_pro_h", "h")
formel("mk_abstreuen", "abstreu_stunden * (abstreuer_stundensatz_eur + abstreuer_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_abstreuen", "abstreu_stunden * stundenlohn_eur * 2", "€")
formel("ent_abstreu", "flaeche_m2 * ent_abstreu_eur_pro_m2", "€")

# Naht aufweiten (widen joint by cutting): cut + clean, by length.
formel("naht_aufweiten_stunden", "laenge_m / naht_aufweiten_leistung_m_pro_h", "h")
formel("mk_naht_aufweiten", "naht_aufweiten_stunden * (schneider_stundensatz_eur + schneider_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_naht_aufweiten", "naht_aufweiten_stunden * stundenlohn_eur * 2", "€")

# Fugenfüllung (joint sealing): hot sealant by joint cross-section + labour.
formel("fugen_menge_t", "fugenspalttiefe_mm * fugenspaltbreite_mm / 1000000 * laenge_m * fugenmasse_dichte_t_pro_m3", "t")
formel("mk_fugenmasse", "fugen_menge_t * fugenmasse_preis_eur_pro_t", "€")
formel("fugenfuellung_stunden", "laenge_m / fugenfuellung_leistung_m_pro_h", "h")
formel("mk_fugenfuellung", "fugenfuellung_stunden * (fugen_geraet_stundensatz_eur + fugen_geraet_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
formel("lohn_fugenfuellung", "fugenfuellung_stunden * stundenlohn_eur * 2", "€")