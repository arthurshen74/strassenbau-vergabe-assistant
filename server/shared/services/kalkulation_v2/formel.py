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
formel("mk_asphalt", "asphalt_stunden * (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l)", "€")
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
formel("lohn_asphalt", "asphalt_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_naht", "naht_stunden * stundenlohn_eur * anzahl_arbeiter", "€")
formel("lohn_erschwernis", "laenge_m * erschwernis_zulage_eur_pro_m", "€")

# --- disposal cost lines ---
formel("ent_boden", "tonnage_abtrag * entsorgung_boden_z2_eur_pro_t", "€")
formel("ent_fraesgut", "tonnage_fraesgut * entsorgung_fraesasphalt_eur_pro_t", "€")
formel("ent_aufbruch", "tonnage_aufbruch * entsorgung_fraesasphalt_eur_pro_t", "€")

# --- transport cost lines ---
formel("trans_material", "tonnage_material * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_boden", "tonnage_abtrag * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_fraesgut", "tonnage_fraesgut * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_aufbruch", "tonnage_aufbruch * transport_eur_pro_t_km * entfernung_km", "€")
formel("trans_asphalt", "menge_t * transport_eur_pro_t_km * entfernung_km", "€")