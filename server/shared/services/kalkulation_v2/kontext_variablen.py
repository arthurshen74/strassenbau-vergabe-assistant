"""
kontext_variablen.py — the Kalkulationskontext variables and their Auflösungsschritte.

These are the SITUATIONAL inputs the StateGraph resolves per position. Each carries
an ordered cascade: try the LV Langtext/Hinweise, then RAG, then a human (HITL).
Geometry placeholders are filled from the LV `menge`. The three "with default"
variables fall back to a KONSTANTE if neither the LV/RAG nor a human supplies them.

Exports KONTEXT_VARIABLEN (variable name -> definition).
"""

from shared.services.kalkulation_v2.model import (
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


def koordinate(name, bez):
    """Baustelle coordinate — REQUIRED, no KONSTANTE fallback: the site location drives
    supplier ranking and must not silently default. Filled by the locate_baustelle node
    (geocoding the Baubeschreibung) before calc; RAG provenance, then a human (HITL)."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez, einheit="°",
        aufloesung=[Schritt(methode=M.RAG,
                            prompt="Standort der Baustelle aus der Baubeschreibung (Adresse, Ort "
                                   "oder Straßenabschnitt) bestimmen; wird geokodiert.",
                            konfidenz_schwelle=D("0.60")),
                    Schritt(methode=M.HITL)])


# --- extracted from the LV / RAG ---
eingabe("tiefe_cm", "Tiefe (Fräs-/Schnitt-/Abtragstiefe)", "cm",
        "Suche im Langtext die Fräs-/Schnitt-/Einbau-/Abtragstiefe; oft als Bereich 'über X bis Y cm'.")
eingabe("markierung_leistung_m_pro_h", "Abtragsleistung Markierung", "m/h",
        "Schätze die Abtragsleistung nach Markierungsstoff (Farbe schnell, Plastik/Thermoplast langsam).")
eingabe("bindemittelmenge_kg_pro_m2", "Bindemittelmenge (Spritzmenge)", "kg/m²",
        "Aus LV-Langtext: Spritzmenge der Bitumenemulsion (kg/m²). Achtung Einheit: g/m² in kg/m² umrechnen.")
eingabe("einbaudicke_cm", "Einbaudicke (Asphaltschicht)", "cm",
        "Aus LV-Langtext: Einbaudicke der Asphaltschicht (cm). Bei t-Abrechnung nicht nötig.")
eingabe("abstreumenge_kg_pro_m2", "Abstreumenge", "kg/m²",
        "Aus LV-Langtext: Menge der Abstreukörnung (kg/m²).")
eingabe("naht_dicke_cm", "Schichtdicke an der Naht", "cm",
        "Aus LV-Langtext: Dicke der Schicht an der Naht (cm); steuert die PmB-Menge (g/m je cm).")
eingabe("fugenspalttiefe_mm", "Fugenspalttiefe", "mm", "Aus LV-Langtext: Fugenspalttiefe (mm).")
eingabe("fugenspaltbreite_mm", "Fugenspaltbreite", "mm", "Aus LV-Langtext: Fugenspaltbreite (mm).")

# Belastungsklasse des Fräsguts — NOT in the position Langtext. It lives in the
# Schadstoff-/PAK-Gutachten of the Vergabeunterlagen, so the cascade is RAG -> HITL
# with NO konstante fallback: the cost swing (verwertbar≈0 vs pechhaltig≈110 €/t) is
# too large to silently default. The agent MUST resolve it.
KONTEXT_VARIABLEN["fraesgut_klasse"] = VarDef(
    name="fraesgut_klasse",
    bezeichnung="Belastungsklasse Fräsgut (1=verwertbar, 2=belastet, 3=pechhaltig)",
    einheit="-",
    aufloesung=[
        Schritt(methode=M.RAG,
                prompt="Belastung des auszubauenden Asphalts bestimmen. Quelle: Schadstoff-/PAK-"
                       "Untersuchung bzw. Bodengutachten der Vergabeunterlagen (NICHT der Positions-"
                       "Langtext). Klassifizieren: 1=verwertbar/unbelastet, 2=belastet (nicht teerhaltig), "
                       "3=pechhaltig/teerhaltig (PAK). Hinweise auf Altbestand (z. B. 'ehem. Sommerweg', "
                       "Pflasterunterlage) erhöhen das Teer-Risiko.",
                konfidenz_schwelle=D("0.80")),
        Schritt(methode=M.HITL)])
eingabe("schichtdicke_m", "Schichtdicke (eingebaut, verdichtet)", "m",
        "Aus Langtext: Dicke der herzustellenden Schicht; oft in cm angegeben (in m umrechnen).")
eingabe("ev2_ziel", "Verdichtungsanforderung Ev2", "MPa",
        "Aus Langtext: geforderter Verformungsmodul Ev2 (MN/m²) auf der fertigen Schicht.")

# --- geometry (one is set per position from `menge`) ---
# flaeche_m2 is intentionally NOT here: when a position is booked in m² it is filled
# directly from `menge` (and the resolver short-circuits on the booked value); when a
# position is booked in m³, flaeche_m2 is DERIVED via volumen_m3 / schichtdicke_m (see formel.py).
for _g, _e in [("laenge_m", "m"), ("volumen_m3", "m³")]:
    geometrie(_g, _e)
# menge_t is NOT a booked placeholder: t-billed positions fill it from `menge`
# (resolver short-circuits); m²-billed asphalt derives it (see formel.py).

# --- Baustelle location (required; geocoded before calc, drives supplier ranking) ---
koordinate("baustelle_breitengrad", "Breitengrad der Baustelle")
koordinate("baustelle_laengengrad", "Längengrad der Baustelle")

# --- situational inputs with a default fallback ---
mit_default("anzahl_arbeiter", "Kolonnenstärke", "Pers", "2", M.HITL)
# Haul distance is split by direction: inbound supply (Antransport, supplier -> Baustelle) is
# filled by supplier selection; outbound disposal (Abtransport, Baustelle -> Deponie) stays HITL.
mit_default("entfernung_lieferant_km", "Entfernung Lieferant → Baustelle (Antransport)", "km", "10", M.HITL)
mit_default("entfernung_deponie_km", "Entfernung Baustelle → Deponie (Abtransport)", "km", "10", M.HITL)
mit_default("erschwernisfaktor", "Erschwerniszuschlag Leistung", "-", "1.0", M.LANGTEXT)