"""
kontext_variablen.py — the Kalkulationskontext variables and their Auflösungsschritte.

These are the SITUATIONAL inputs the StateGraph resolves per position. Each carries an
ordered cascade: try the LV Langtext/Hinweise, then RAG, then a human (HITL). Geometry
placeholders are filled from the LV `menge`. The "with default" variables fall back to a
KONSTANTE if neither the LV/RAG nor a human supplies them.

Every variable carries retrieval-grade `beschreibung` (REZEPT_REDESIGN_PLAN §2.6): meaning,
which base-formula parameter it feeds, and traps — co-authored with the cascade prompts (the
executable "how to find it") so prose and enforcement cannot drift.

Exports KONTEXT_VARIABLEN (variable name -> definition).
"""

from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M, AufloesungsSchritt as Schritt, D, VariableDefinition as VarDef,
)

KONTEXT_VARIABLEN: dict[str, VarDef] = {}


def eingabe(name, bez, einheit, rag_prompt, beschreibung):
    """Extracted input: LV Langtext -> RAG -> HITL. `rag_prompt` is the executable retrieval
    intent; `beschreibung` is the human-readable meaning (co-authored, must not drift)."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez, beschreibung=beschreibung,
        einheit=einheit, llm_kontext=rag_prompt,
        aufloesung=[Schritt(methode=M.LANGTEXT, prompt=f"Aus LV-Langtext/Hinweisen: {bez} ({einheit}).",
                            konfidenz_schwelle=D("0.75")),
                    Schritt(methode=M.RAG, prompt=rag_prompt, konfidenz_schwelle=D("0.60")),
                    Schritt(methode=M.HITL)])


def geometrie(name, einheit, beschreibung):
    """Geometry placeholder — filled from the LV menge before calc (GEOM[einheit] = name)."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=name, beschreibung=beschreibung,
                                     einheit=einheit, aufloesung=[Schritt(methode=M.HITL)])


def mit_default(name, bez, einheit, default, erststufe, beschreibung, prompt=None):
    """Situational input whose true source is `erststufe` (HITL/LANGTEXT), with a
    KONSTANTE fallback so the calc still runs when nobody overrides it. A LANGTEXT/RAG
    erststufe carries a co-authored `prompt` (the executable retrieval intent)."""
    KONTEXT_VARIABLEN[name] = VarDef(name=name, bezeichnung=bez, beschreibung=beschreibung,
        einheit=einheit,
        aufloesung=[Schritt(methode=erststufe, prompt=prompt),
                    Schritt(methode=M.KONSTANTE, konstante=D(default))])


# --- extracted from the LV / RAG ---
eingabe("tiefe_cm", "Tiefe (Fräs-/Schnitt-/Abtragstiefe)", "cm",
        "Suche im Langtext die Fräs-/Schnitt-/Einbau-/Abtragstiefe; oft als Bereich 'über X bis Y cm'.",
        beschreibung="Arbeitstiefe in cm (Fräsen, Schneiden, Aufbrechen). Treibt die tiefenabhängige "
                     "Leistung (tiefe-Parameter von F_LEISTUNG_TIEFE) UND die Fräsgut-/Aufbruchtonnage "
                     "(dicke von F_VOLUMEN_FLAECHE). Der Konverter skaliert cm→m an der Bindung.")
eingabe("markierung_leistung_m_pro_h", "Abtragsleistung Markierung", "m/h",
        "Schätze die Abtragsleistung nach Markierungsstoff (Farbe schnell, Plastik/Thermoplast langsam).",
        beschreibung="Abtragsleistung der Demarkierung je laufendem Meter und Stunde; leistung-Parameter "
                     "von F_STUNDEN. Hängt stark am Markierungsstoff — situativ je Position, kein fester Satz.")
eingabe("bindemittelmenge_kg_pro_m2", "Bindemittelmenge (Spritzmenge)", "kg/m²",
        "Aus LV-Langtext: Spritzmenge der Bitumenemulsion (kg/m²). Achtung Einheit: g/m² in kg/m² umrechnen.",
        beschreibung="Spritzmenge Bitumenemulsion je m² (Schichtenverbund); ansatz-Parameter von "
                     "F_MENGE_ANSATZ (× Fläche → t, der Konverter normalisiert kg→t). Achtung: g/m² "
                     "in kg/m² umrechnen.")
eingabe("einbaudicke_cm", "Einbaudicke (Asphaltschicht)", "cm",
        "Aus LV-Langtext: Einbaudicke der Asphaltschicht (cm). Bei t-Abrechnung nicht nötig.",
        beschreibung="Einbaudicke der Asphaltschicht in cm; dicke-Parameter von F_VOLUMEN_FLAECHE für "
                     "die m²→t-Tonnage. Bei t-abgerechneten Positionen ungenutzt (menge_t ist gebucht).")
eingabe("abstreumenge_kg_pro_m2", "Abstreumenge", "kg/m²",
        "Aus LV-Langtext: Menge der Abstreukörnung (kg/m²).",
        beschreibung="Abstreumenge (Körnung) je m²; ansatz-Parameter von F_MENGE_ANSATZ für die "
                     "Abstumpfungs-Materialmenge (× Fläche → t, kg→t konvertiert).")
eingabe("naht_dicke_cm", "Schichtdicke an der Naht", "cm",
        "Aus LV-Langtext: Dicke der Schicht an der Naht (cm); steuert die PmB-Menge (g/m je cm).",
        beschreibung="Schichtdicke an der Naht in cm; bezugsmenge der ersten Stufe der zweistufigen "
                     "Naht-Mengenrechnung (naht_material_g_pro_m_cm × Nahtdicke → t/m, dann × Länge → t).")
eingabe("fugenspalttiefe_mm", "Fugenspalttiefe", "mm", "Aus LV-Langtext: Fugenspalttiefe (mm).",
        beschreibung="Tiefe des Fugenspalts in mm; tiefe-Kante von F_VOLUMEN_QUADER für das "
                     "Fugenmassevolumen (Breite × Tiefe × Länge). Der Konverter skaliert mm→m.")
eingabe("fugenspaltbreite_mm", "Fugenspaltbreite", "mm", "Aus LV-Langtext: Fugenspaltbreite (mm).",
        beschreibung="Breite des Fugenspalts in mm; breite-Kante von F_VOLUMEN_QUADER für das "
                     "Fugenmassevolumen. Der Konverter skaliert mm→m.")

# Belastungsklasse des Fräsguts — NOT in the position Langtext. It lives in the
# Schadstoff-/PAK-Gutachten of the Vergabeunterlagen, so the cascade is RAG -> HITL
# with NO konstante fallback: the cost swing (verwertbar≈0 vs pechhaltig≈110 €/t) is
# too large to silently default. The agent MUST resolve it.
KONTEXT_VARIABLEN["fraesgut_klasse"] = VarDef(
    name="fraesgut_klasse",
    bezeichnung="Belastungsklasse Fräsgut (1=verwertbar, 2=belastet, 3=pechhaltig)",
    beschreibung="Belastungsklasse des auszubauenden Asphalts (1 verwertbar, 2 belastet, 3 pechhaltig/"
                 "teerhaltig); wert-Parameter von F_STAFFEL, wählt den Entsorgungssatz. Der Satz-"
                 "unterschied ist erheblich (≈0 vs. ≈110 €/t) — daher KEIN Default, die Klasse MUSS "
                 "aufgelöst werden. Quelle ist das Schadstoffgutachten, nicht der Positions-Langtext.",
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
        "Aus Langtext: Dicke der herzustellenden Schicht; oft in cm angegeben (in m umrechnen).",
        beschreibung="Dicke der herzustellenden, verdichteten Schicht in m; treibt die Fläche aus "
                     "gebuchtem Volumen (dicke von F_FLAECHE_VOLUMEN) und die Lagenzahl (dicke von "
                     "F_LAGEN). Oft im LV in cm — in m umrechnen.")
eingabe("ev2_ziel", "Verdichtungsanforderung Ev2", "MPa",
        "Aus Langtext: geforderter Verformungsmodul Ev2 (MN/m²) auf der fertigen Schicht.",
        beschreibung="Geforderter Verformungsmodul Ev2 (MN/m²) auf der fertigen Schicht; x-Parameter "
                     "von F_UEBERGAENGE, das daraus die Walzübergangszahl interpoliert. Höheres Ev2 → "
                     "mehr Übergänge → mehr Walzzeit.")

# --- geometry (one is set per position from `menge`) ---
# flaeche_m2 and menge_t are placeholders like the others: booked directly when the
# position bills in that unit; otherwise the Vorgang derives them via an instanz that
# declares `variable` (F_FLAECHE_VOLUMEN / the Asphalt-Tonnage chain in vorgaenge.py).
geometrie("flaeche_m2", "m²",
          beschreibung="Gebuchte Fläche der LV-Position in m² (bei m²-Abrechnung aus der Menge "
                       "gefüllt); Bezugsgröße vieler F_STUNDEN-Instanzen. Bei m³-Abrechnung von einer "
                       "Instanz aus Volumen/Schichtdicke hergeleitet (materialisiert flaeche_m2).")
geometrie("laenge_m", "m",
          beschreibung="Gebuchte Länge der LV-Position in m (bei m-Abrechnung aus der Menge gefüllt); "
                       "Bezugsgröße der laufenden-Meter-Vorgänge (Naht, Fugen, Markierung, "
                       "Randabdichtung, Erschwernis).")
geometrie("volumen_m3", "m³",
          beschreibung="Gebuchtes Volumen der LV-Position in m³ (bei m³-Abrechnung aus der Menge "
                       "gefüllt); Bezugsgröße für Schüttgut-Einbau/Abtrag und Ausgangsgröße der "
                       "Tonnage (F_MENGE_VOLUMEN) und der Fläche (F_FLAECHE_VOLUMEN).")
geometrie("menge_t", "t",
          beschreibung="Gebuchte Tonnage der LV-Position in t (bei t-Abrechnung aus der Menge gefüllt); "
                       "Bezugsgröße des Asphalteinbaus. Bei m²-Abrechnung von der Asphalt-Tonnagekette "
                       "hergeleitet (materialisiert menge_t) — dann ist die gebuchte Menge nicht gesetzt.")
geometrie("anzahl_st", "St",
          beschreibung="Gebuchte Stückzahl der LV-Position (bei St-Abrechnung aus der Menge gefüllt); "
                       "Bezugsgröße stückweiser Vorgänge (z. B. Schieberkappen regulieren).")
# menge_t is NOT a booked-only placeholder: t-billed positions fill it from `menge`;
# m²-billed asphalt derives it (see vorgaenge.py). Baustelle coordinates are NOT engine
# variables: the site location is a project-level global (project_context) and drives
# supplier ranking / deponie routing in the graph, not a formula.

# --- situational inputs with a default fallback ---
mit_default("anzahl_arbeiter", "Kolonnenstärke", "Pers", "2", M.HITL,
            beschreibung="Kolonnenstärke des Vorgangs (Zahl Arbeiter); kolonne-Parameter von F_LOHN. "
                         "Situativ je Position geprüft, Standard 2 — die Angabe des Kalkulators "
                         "('zwei Mann') ist der Erwartungswert, kein fester Satz.")
# Haul distance is split by direction: inbound supply (Antransport, supplier -> Baustelle) is
# filled by supplier selection; outbound disposal (Abtransport, Baustelle -> Deponie) stays HITL.
mit_default("entfernung_lieferant_km", "Entfernung Lieferant → Baustelle (Antransport)", "km", "10", M.HITL,
            beschreibung="Entfernung Lieferant → Baustelle in km (Antransport); entfernung-Parameter "
                         "von F_TRANSPORT für gelieferte Baustoffe. Wird von der Lieferantenauswahl "
                         "gefüllt, Standard 10.")
mit_default("entfernung_deponie_km", "Entfernung Baustelle → Deponie (Abtransport)", "km", "10", M.HITL,
            beschreibung="Entfernung Baustelle → Deponie in km (Abtransport); entfernung-Parameter von "
                         "F_TRANSPORT für Abtrag/Fräsgut. Aus dem Deponie-Routing, Standard 10.")
mit_default("erschwernisfaktor", "Erschwerniszuschlag Leistung", "-", "1.0", M.LANGTEXT,
            beschreibung="Erschwernisfaktor (≥1) für beengte/schwierige Verhältnisse; erschwernisfaktor-"
                         "Parameter von F_LEISTUNG_TIEFE / F_LEISTUNG_ERSCHWERT — teilt die Leistung, "
                         "verlängert also die Zeit. 1.0 = Normalbedingungen.",
            prompt="Aus LV-Langtext/Hinweisen: erschwerte Bedingungen, die die Leistung mindern — "
                   "Kleinflächen, Handarbeit, beengte/innerstädtische Lage, Nachtbaustelle, Arbeiten "
                   "unter Verkehr. Faktor ≥1 schätzen (1.0 Normalbedingungen); ohne Hinweis 1.0.")
