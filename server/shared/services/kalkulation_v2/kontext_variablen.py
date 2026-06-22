"""
kontext_variablen.py — the Kalkulationskontext variables and their Auflösungsschritte.

These are the SITUATIONAL inputs the StateGraph resolves per position. Each carries
an ordered cascade: try the LV Langtext/Hinweise, then RAG, then a human (HITL).
Geometry placeholders are filled from the LV `menge`. The three "with default"
variables fall back to a KONSTANTE if neither the LV/RAG nor a human supplies them.

Exports KONTEXT_VARIABLEN (variable name -> definition).
"""

from model import (
    AufloesungsMethode as M, AufloesungsSchritt as Schritt, D, VariableDefinition as VarDef,
)

KONTEXT_VARIABLEN: dict[str, VarDef] = {}


def eingabe(name, bez, einheit, rag_prompt):
    """Extracted input: LV Langtext -> RAG -> HITL."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez, einheit=einheit,
        aufloesung=[Schritt(methode=M.LANGTEXT, prompt=f"Aus LV-Langtext/Hinweisen: {bez} ({einheit}).",
                            konfidenz_schwelle=D("0.75")),
                    Schritt(methode=M.RAG, prompt=rag_prompt, konfidenz_schwelle=D("0.60")),
                    Schritt(methode=M.HITL)])


def geometrie(name, einheit):
    """Geometry placeholder — filled from the LV menge before calc."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=name, einheit=einheit,
                                     aufloesung=[Schritt(methode=M.HITL)])


def mit_default(name, bez, einheit, default, erststufe):
    """Situational input whose true source is `erststufe` (HITL/LANGTEXT), with a
    KONSTANTE fallback so the calc still runs when nobody overrides it."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez, einheit=einheit,
        aufloesung=[Schritt(methode=erststufe),
                    Schritt(methode=M.KONSTANTE, konstante=D(default))])


# --- extracted from the LV / RAG ---
eingabe("tiefe_cm", "Tiefe (Fräs-/Schnitt-/Abtragstiefe)", "cm",
        "Suche im Langtext die Fräs-/Schnitt-/Einbau-/Abtragstiefe; oft als Bereich 'über X bis Y cm'.")
eingabe("markierung_leistung_m_pro_h", "Abtragsleistung Markierung", "m/h",
        "Schätze die Abtragsleistung nach Markierungsstoff (Farbe schnell, Plastik/Thermoplast langsam).")
# NOTE: true source is STAMMDATEN (supplier price list) once a Lieferant is chosen.
eingabe("materialpreis_eur_pro_t", "Materialpreis", "€/t",
        "Materialpreis des gewählten Baustoffs beim Lieferanten zum Stichtag.")

# --- geometry (one is set per position from `menge`) ---
for _g, _e in [("flaeche_m2", "m²"), ("laenge_m", "m"), ("volumen_m3", "m³"), ("menge_t", "t")]:
    geometrie(_g, _e)

# --- situational inputs with a default fallback ---
mit_default("anzahl_arbeiter", "Kolonnenstärke", "Pers", "2", M.HITL)
mit_default("entfernung_km", "Entfernung Lager/Deponie", "km", "10", M.HITL)   # ideally computed from coords
mit_default("erschwernisfaktor", "Erschwerniszuschlag Leistung", "-", "1.0", M.LANGTEXT)