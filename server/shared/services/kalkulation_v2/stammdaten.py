"""
stammdaten.py — Kostenstammdaten: the rate book.

Org-global KONSTANTE rates (fuel, wages, machine rates, disposal, fixed outputs) plus
the STAMMDATEN bridge variables that pull physical properties from the material catalog.
These are reference data — slow-moving, editable in the UI, the same for every
bid. Every entry carries retrieval-grade `beschreibung` (REZEPT_REDESIGN_PLAN §2.6):
what the value is, which base-formula parameter it feeds, and how it is maintained — so
the Rezept-Compiler finds the existing Satz instead of minting a new one. Exports
STAMMDATEN_VARIABLEN (variable name -> definition).
"""

from shared.services.kalkulation_v2.model import (
    AufloesungsMethode as M,
    AufloesungsSchritt as Schritt,
    D,
    VariableDefinition as VarDef,
)

STAMMDATEN_VARIABLEN: dict[str, VarDef] = {}


def konst(name, wert, einheit, beschreibung, bez=None):
    STAMMDATEN_VARIABLEN[name] = VarDef(
        name=name,
        bezeichnung=bez or name,
        beschreibung=beschreibung,
        einheit=einheit,
        aufloesung=[Schritt(methode=M.KONSTANTE, konstante=D(wert))],
    )


def stammdaten(name, pfad, einheit, beschreibung, bez=None):
    STAMMDATEN_VARIABLEN[name] = VarDef(
        name=name,
        bezeichnung=bez or name,
        beschreibung=beschreibung,
        einheit=einheit,
        aufloesung=[Schritt(methode=M.STAMMDATEN, stammdaten_pfad=pfad)],
    )


def stammdaten_mit_default(name, pfad, default, einheit, beschreibung, bez=None):
    """A master-data bridge with a KONSTANTE fallback: read `pfad` off the chosen
    Baustoff (e.g. its basispreis), else fall back to `default` when no Baustoff is
    bound. A per- position kontext value still overrides both (resolve() checks
    ctx.werte first)."""
    STAMMDATEN_VARIABLEN[name] = VarDef(
        name=name,
        bezeichnung=bez or name,
        beschreibung=beschreibung,
        einheit=einheit,
        aufloesung=[
            Schritt(methode=M.STAMMDATEN, stammdaten_pfad=pfad),
            Schritt(methode=M.KONSTANTE, konstante=D(default)),
        ],
    )


# --- global rates ---
konst(
    "kraftstoffpreis_eur_pro_l",
    "1.75",
    "€/l",
    bez="Kraftstoffpreis",
    beschreibung="Dieselpreis je Liter; speist den kraftstoffpreis-Parameter von "
    "F_MASCHINE in "
    "JEDER Maschinenkostenzeile. Ein Firmenwert, gepflegt mit aendere_stammdaten_wert "
    "— eine Änderung schlägt auf alle Vorgänge durch.",
)
konst(
    "stundenlohn_eur",
    "42.00",
    "€/h",
    bez="Stundenlohn",
    beschreibung="Kalkulatorischer Mittellohn je gewerblichem Mitarbeiter "
    "(Kolonnenlohn inkl. "
    "Zuschlägen); speist den stundenlohn-Parameter von F_LOHN. Firmensatz, gilt für "
    "jede Lohnzeile.",
)
konst(
    "transport_eur_pro_t_km",
    "0.12",
    "€/(t·km)",
    bez="Transportsatz",
    beschreibung="Frachtsatz je Tonne und Kilometer; speist den satz-Parameter von "
    "F_TRANSPORT "
    "(An- wie Abtransport). Firmensatz.",
)

# --- machine rates (incl. Verschleiß) --- Each pair (stundensatz_eur / l_pro_h) is the
# no-machine default for F_MASCHINE's stundensatz / verbrauch parameters — a bound
# Maschine overrides them from its property bag (kosten_bindung).
konst(
    "bagger_stundensatz_eur",
    "110",
    "€/h",
    bez="Baggerstundensatz",
    beschreibung="Gerätestundensatz Hydraulikbagger inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-"
    "Default für Bagger-Vorgänge (Abtrag, Aufbruch), sofern keine Maschine gebunden "
    "ist.",
)
konst(
    "bagger_l_pro_h",
    "17",
    "l/h",
    beschreibung="Kraftstoffverbrauch Hydraulikbagger je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "radlader_stundensatz_eur",
    "70",
    "€/h",
    bez="Radladerstundensatz",
    beschreibung="Gerätestundensatz Radlader inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default für "
    "Schüttgut-Einbau (Liefern/Legen).",
)
konst(
    "radlader_l_pro_h",
    "14",
    "l/h",
    beschreibung="Kraftstoffverbrauch Radlader je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "walze_stundensatz_eur",
    "50",
    "€/h",
    bez="Walzenstundensatz",
    beschreibung="Gerätestundensatz Verdichtungswalze inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-"
    "Default für Verdichtungs-Vorgänge.",
)
konst(
    "walze_l_pro_h",
    "9",
    "l/h",
    beschreibung="Kraftstoffverbrauch Walze je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "kaltfraese_stundensatz_eur",
    "210",
    "€/h",
    bez="Kaltfräsenstundensatz",
    beschreibung="Gerätestundensatz Kaltfräse inkl. Verschleiß (Meißel!); "
    "F_MASCHINE-stundensatz-"
    "Default für Fräsen und Feinfräsen.",
)
konst(
    "kaltfraese_l_pro_h",
    "60",
    "l/h",
    beschreibung="Kraftstoffverbrauch Kaltfräse je Betriebsstunde (hoch — Fräswalze); "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "schneider_stundensatz_eur",
    "42",
    "€/h",
    bez="Fugenschneiderstundensatz",
    beschreibung="Gerätestundensatz Fugenschneider inkl. Verschleiß (Trennscheibe); "
    "F_MASCHINE-stundensatz-Default für Trennen/Schneiden/Naht-Aufweiten.",
)
konst(
    "schneider_l_pro_h",
    "4",
    "l/h",
    beschreibung="Kraftstoffverbrauch Fugenschneider je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "markfraese_stundensatz_eur",
    "60",
    "€/h",
    bez="Markierungsfräsenstundensatz",
    beschreibung="Gerätestundensatz Markierungsfräse inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-"
    "Default für Demarkierung.",
)
konst(
    "markfraese_l_pro_h",
    "6",
    "l/h",
    beschreibung="Kraftstoffverbrauch Markierungsfräse je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "aufbruch_stundensatz_eur",
    "130",
    "€/h",
    bez="Aufbruchbaggerstundensatz",
    beschreibung="Gerätestundensatz Bagger mit Hydraulikmeißel inkl. Verschleiß; "
    "F_MASCHINE-"
    "stundensatz-Default für Asphalt-/Betonaufbruch (höher als der reine Bagger).",
)
konst(
    "aufbruch_l_pro_h",
    "20",
    "l/h",
    beschreibung="Kraftstoffverbrauch Aufbruchbagger je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "grader_stundensatz_eur",
    "95",
    "€/h",
    bez="Graderstundensatz",
    beschreibung="Gerätestundensatz Motorgrader inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default "
    "für Profilieren/Planum.",
)
konst(
    "grader_l_pro_h",
    "14",
    "l/h",
    beschreibung="Kraftstoffverbrauch Grader je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "naht_geraet_stundensatz_eur",
    "25",
    "€/h",
    bez="Nahtgerätstundensatz",
    beschreibung="Gerätestundensatz Nahtband-/Fugengerät inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-"
    "Default für die Nahtherstellung.",
)
konst(
    "naht_geraet_l_pro_h",
    "3",
    "l/h",
    beschreibung="Kraftstoffverbrauch Nahtgerät je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)

# --- material / disposal rates ---
konst(
    "dichte_asphalt_t_pro_m3",
    "2.40",
    "t/m³",
    bez="Rohdichte Asphalt",
    beschreibung="Rohdichte von Asphalt (verdichtet); der m³→t-Übergang für flächig "
    "gebuchte "
    "Asphaltmengen und für Fräsgut/Aufbruch (dichte-Parameter von F_MENGE_VOLUMEN). "
    "Materialkonstante, kein Baustoff-Feld, da für Fräsgut kein Baustoff gebunden ist.",
)
# Fräsgut disposal/recycling by Belastungsklasse — feed F_STAFFEL's satz1/satz2/satz3.
# PLACEHOLDERS — set from the Schadstoffgutachten of the Vergabeunterlagen.
konst(
    "ent_fraesgut_verwertbar",
    "0.00",
    "€/t",
    bez="Entsorgung Fräsgut Klasse 1",
    beschreibung="Entsorgungs-/Verwertungssatz für unbelastetes Fräsgut "
    "(Belastungsklasse 1); "
    "oft eine Gutschrift, hier 0. F_STAFFEL-satz1 nach fraesgut_klasse. PLATZHALTER — "
    "aus dem Schadstoffgutachten setzen.",
)
konst(
    "ent_fraesgut_belastet",
    "25.00",
    "€/t",
    bez="Entsorgung Fräsgut Klasse 2",
    beschreibung="Entsorgungssatz für belastetes, nicht teerhaltiges Fräsgut "
    "(Belastungsklasse 2); "
    "F_STAFFEL-satz2. PLATZHALTER — aus dem Schadstoffgutachten setzen.",
)
konst(
    "ent_fraesgut_pechhaltig",
    "110.00",
    "€/t",
    bez="Entsorgung Fräsgut Klasse 3",
    beschreibung="Entsorgungssatz für pechhaltiges/teerhaltiges Fräsgut (PAK, "
    "Sonderabfall, "
    "Belastungsklasse 3) — deutlich teurer. F_STAFFEL-satz3. PLATZHALTER — aus dem "
    "Schadstoffgutachten setzen; niemals eine Klasse annehmen.",
)
konst(
    "entsorgung_boden_z2_eur_pro_t",
    "16.00",
    "€/t",
    bez="Entsorgung Boden Z2",
    beschreibung="Entsorgungssatz für abgetragenen Boden der Einbauklasse Z2 (LAGA); "
    "satz-Parameter "
    "der Boden-Entsorgungszeile (F_KOSTEN_SATZ).",
)
konst(
    "erschwernis_zulage_eur_pro_m",
    "8.50",
    "€/m",
    bez="Erschwernis-Zulage je Meter",
    beschreibung="Zulagensatz je laufendem Meter Einfassung/Erschwernis (Bordsteine, "
    "Schächte, "
    "Anschlüsse); satz-Parameter der Erschwernis-Zulage (F_KOSTEN_SATZ, Kostenart "
    "Lohn).",
)
konst(
    "entsorgung_demark_eur_pro_m",
    "0.15",
    "€/m",
    bez="Entsorgung Demarkierungsabfall",
    beschreibung="Satz je laufendem Meter für Aufnahme und Verwertung des "
    "Demarkierungsabfalls; "
    "satz-Parameter der Demarkierungs-Entsorgungszeile. PLATZHALTER.",
)
# Asphalt mix price comes from the selected Baustoff (AC/SMA basispreis); Default AC 32
# T S when no mix is bound. So the asphalt recipe now needs a Baustoff
# (braucht_baustoff=True).
stammdaten_mit_default(
    "asphalt_preis_eur_pro_t",
    "baustoff.basispreis_eur",
    "72.00",
    "€/t",
    bez="Asphaltmischgutpreis",
    beschreibung="Preis Asphaltmischgut je Tonne — der Basispreis des gewählten "
    "Baustoffs (AC/SMA), sonst Default AC 32 T S. satz-Parameter der "
    "Asphalt-Materialzeile; braucht einen gebundenen Baustoff.",
)
stammdaten_mit_default(
    "pmb_preis_eur_pro_t",
    "baustoff.basispreis_eur",
    "850.00",
    "€/t",
    bez="PmB-Nahtbindemittelpreis",
    beschreibung="Preis polymermodifiziertes Bitumen (PmB) für Nahtband je Tonne — "
    "Baustoff-Basispreis. satz-Parameter der Naht-Materialzeile.",
)
konst(
    "naht_material_g_pro_m_cm",
    "50",
    "g/(m·cm)",
    bez="Nahtbindemittel-Ansatz",
    beschreibung="Ansatz PmB-Nahtmaterial je laufendem Meter und cm Schichtdicke; "
    "ansatz-Parameter "
    "der zweistufigen Naht-Mengenrechnung (× Nahtdicke → t/m, dann × Länge → t). "
    "Der Konverter normalisiert g→t.",
)
# naht_dicke_cm is now per-position (LANGTEXT) — see kontext_variablen.py

# --- fixed machine outputs (depth-independent) --- feed F_STUNDEN's leistung parameter.
konst(
    "einbau_leistung_m3_pro_h",
    "35",
    "m³/h",
    bez="Einbauleistung Mineralstoff",
    beschreibung="Einbauleistung des kombinierten Mineralstoffeinbaus (Radlader + "
    "Walze) je "
    "Stunde, bezogen auf das Volumen; leistung-Parameter von F_STUNDEN für V_EINBAU.",
)
konst(
    "bagger_leistung_m3_pro_h",
    "45",
    "m³/h",
    bez="Aushubleistung Bagger",
    beschreibung="Aushub-/Abtragsleistung Bagger je Stunde (Volumen); "
    "leistung-Parameter von "
    "F_STUNDEN für den Bodenabtrag.",
)
konst(
    "planum_leistung_m2_pro_h",
    "250",
    "m²/h",
    bez="Planumleistung Grader",
    beschreibung="Herstellleistung Planum (Grader + Walze) je Stunde, flächenbezogen; "
    "leistung-"
    "Parameter von F_STUNDEN für V_PLANUM.",
)
konst(
    "walze_leistung_m2_pro_h",
    "400",
    "m²/h",
    bez="Verdichtungsleistung Walze",
    beschreibung="Flächenleistung Bodenverdichtung Walze je Stunde (einlagig, ohne "
    "Übergangs-"
    "staffelung); leistung-Parameter von F_STUNDEN für V_VERDICHTEN.",
)
konst(
    "asphalt_einbau_leistung_t_pro_h",
    "90",
    "t/h",
    bez="Asphalt-Einbauleistung Fertiger",
    beschreibung="Einbauleistung des maschinellen Asphaltzugs (Fertiger + Beschicker + "
    "Walzen) je "
    "Stunde, tonnenbezogen; leistung-Parameter von F_STUNDEN für den Asphalteinbau.",
)
konst(
    "naht_leistung_m_pro_h",
    "150",
    "m/h",
    bez="Nahtleistung",
    beschreibung="Herstellleistung Naht je laufendem Meter und Stunde; "
    "leistung-Parameter von "
    "F_STUNDEN für V_NAHT.",
)

# --- FSS decomposition: lay / profile / compact rates (PLACEHOLDERS – set in rate book)
# ---
konst(
    "radlader_leistung_m3_pro_h",
    "40",
    "m³/h",
    bez="Liefer-/Legeleistung Radlader (FSS)",
    beschreibung="Liefer-/Legeleistung Radlader für Frostschutzschicht je Stunde "
    "(Volumen); "
    "leistung-Parameter von F_STUNDEN für FSS_LEGEN. PLATZHALTER.",
)
konst(
    "profil_leistung_m2_pro_h",
    "500",
    "m²/h",
    bez="Profilierleistung Grader (je Lage)",
    beschreibung="Profilierleistung Grader je Stunde und Lage (flächenbezogen); "
    "leistung-Parameter "
    "von F_STUNDEN für FSS_PROFIL, mehrlagig über F_ARBEITSMENGE. PLATZHALTER.",
)
konst(
    "walze_uebergang_leistung_m2_pro_h",
    "1200",
    "m²/(h·Übergang)",
    bez="Walzleistung je Übergang (FSS)",
    beschreibung="Walzleistung je Stunde und Übergang für die FSS-Verdichtung; "
    "leistung-Parameter "
    "von F_STUNDEN, wobei die Übergangszahl aus F_UEBERGAENGE (Ev2) in die "
    "Arbeitsmenge "
    "eingeht. PLATZHALTER.",
)
konst(
    "fertiger_stundensatz_eur",
    "180",
    "€/h",
    bez="Fertigerstundensatz",
    beschreibung="Gerätestundensatz Straßenfertiger inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-"
    "Default für den FSS-Fertiger-Einbau.",
)
konst(
    "fertiger_l_pro_h",
    "25",
    "l/h",
    beschreibung="Kraftstoffverbrauch Fertiger je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "fertiger_leistung_m2_pro_h",
    "600",
    "m²/h",
    bez="Einbauleistung Fertiger (ein Zug)",
    beschreibung="Einbau- und Abziehleistung Fertiger je Stunde in einem Zug "
    "(flächenbezogen); "
    "leistung-Parameter von F_STUNDEN für FSS_FERTIGER. PLATZHALTER.",
)
konst(
    "max_lagendicke_b2_m",
    "0.30",
    "m",
    bez="Max. Lagendicke B2 0/32",
    beschreibung="Maximal verdichtbare Lagendicke für Mineralgemisch B2 0/32; "
    "max_lagendicke-"
    "Parameter von F_LAGEN (Schichtdicke ÷ diese Dicke, aufgerundet). "
    "Norm-/Materialwissen.",
)
# Ev2 target -> Walzübergänge: F_UEBERGAENGE anchors — Verdichtungs-Firmenwissen.
konst(
    "verdicht_uebergaenge_ev45",
    "3",
    "-",
    bez="Walzübergänge bei Ev2=45",
    beschreibung="Anzahl Walzübergänge am unteren Ev2-Anker (45 MPa); y0-Parameter von "
    "F_UEBERGAENGE (geklemmte lineare Interpolation über das Ev2-Ziel).",
)
konst(
    "verdicht_uebergaenge_ev100",
    "6",
    "-",
    bez="Walzübergänge bei Ev2=100",
    beschreibung="Anzahl Walzübergänge am oberen Ev2-Anker (100 MPa); y1-Parameter von "
    "F_UEBERGAENGE.",
)
konst(
    "ev2_anker_min",
    "45",
    "MPa",
    bez="Unterer Ev2-Anker",
    beschreibung="Unterer Stützpunkt der Ev2→Übergänge-Kurve (x0 von F_UEBERGAENGE). "
    "Verdichtungs-Firmenwissen.",
)
konst(
    "ev2_anker_max",
    "100",
    "MPa",
    bez="Oberer Ev2-Anker",
    beschreibung="Oberer Stützpunkt der Ev2→Übergänge-Kurve (x1 von F_UEBERGAENGE).",
)

# --- Bankettbefestigung: narrow-strip productivity + dedicated gear (PLACEHOLDERS) ---
konst(
    "bankett_legen_leistung_m3_pro_h",
    "25",
    "m³/h",
    bez="Liefer-/Legeleistung Radlader (Bankett)",
    beschreibung="Liefer-/Legeleistung Radlader für Bankettmaterial je Stunde "
    "(Volumen, langsamer "
    "als FSS wegen ~1 m schmalem Streifen); leistung-Parameter von F_STUNDEN für "
    "BANKETT_LEGEN. PLATZHALTER.",
)
konst(
    "bankett_profil_leistung_m2_pro_h",
    "300",
    "m²/h",
    bez="Profilierleistung Grader (Bankett)",
    beschreibung="Profilierleistung Grader für Bankette je Stunde und Lage; "
    "leistung-Parameter von "
    "F_STUNDEN für BANKETT_PROFIL. PLATZHALTER.",
)
konst(
    "bankettwalze_stundensatz_eur",
    "45",
    "€/h",
    bez="Bankettwalzenstundensatz",
    beschreibung="Gerätestundensatz kleine Tandemwalze (Bankett) inkl. Verschleiß; "
    "F_MASCHINE-"
    "stundensatz-Default für die Bankettverdichtung.",
)
konst(
    "bankettwalze_l_pro_h",
    "6",
    "l/h",
    beschreibung="Kraftstoffverbrauch Bankett-Tandemwalze je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "bankettwalze_uebergang_leistung_m2_pro_h",
    "700",
    "m²/(h·Übergang)",
    bez="Walzleistung je Übergang (Bankett)",
    beschreibung="Walzleistung je Stunde und Übergang für die Bankettverdichtung "
    "(niedriger "
    "als FSS); leistung-Parameter von F_STUNDEN mit F_UEBERGAENGE-Übergangszahl. "
    "PLATZHALTER.",
)
konst(
    "bankettfertiger_stundensatz_eur",
    "120",
    "€/h",
    bez="Bankettfertigerstundensatz",
    beschreibung="Gerätestundensatz Bankettfertiger inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default "
    "für den Bankett-Fertiger-Einbau.",
)
konst(
    "bankettfertiger_l_pro_h",
    "14",
    "l/h",
    beschreibung="Kraftstoffverbrauch Bankettfertiger je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "bankettfertiger_leistung_m2_pro_h",
    "350",
    "m²/h",
    bez="Einbauleistung Bankettfertiger",
    beschreibung="Einbau- und Abziehleistung Bankettfertiger je Stunde (Quergefälle in "
    "einem Zug); "
    "leistung-Parameter von F_STUNDEN für BANKETT_FERTIGER. PLATZHALTER.",
)

# --- Grobkörniger Boden (Auffüllung unter Banketten, Einzelflächen) — PLACEHOLDERS ---
# LV nennt KEIN Ev2/DPr -> fester Übergangs-Ansatz (Standardverdichtung), nicht
# Ev2-getrieben.
konst(
    "boden_legen_leistung_m3_pro_h",
    "30",
    "m³/h",
    bez="Liefer-/Einbauleistung Radlader (Boden)",
    beschreibung="Liefer-/Einbauleistung Radlader für grobkörnigen Boden je Stunde "
    "(Volumen, "
    "Einzelflächen → niedrig); leistung-Parameter von F_STUNDEN für BODEN_GROBK_LEGEN. "
    "PLATZHALTER.",
)
konst(
    "boden_profil_leistung_m2_pro_h",
    "250",
    "m²/h",
    bez="Profil-/Planumleistung Grader (Boden)",
    beschreibung="Profilier-/Planumleistung Grader für grobkörnigen Boden je Stunde "
    "und Lage "
    "(Planum einbegriffen); leistung-Parameter von F_STUNDEN für BODEN_GROBK_PROFIL. "
    "PLATZHALTER.",
)
konst(
    "boden_verdicht_uebergaenge",
    "4",
    "-",
    bez="Walzübergänge Boden (fest)",
    beschreibung="Fester Ansatz Walzübergänge für die Standardverdichtung grobkörnigen "
    "Bodens — "
    "das LV nennt kein Ev2/DPr, daher NICHT die Ev2-Kurve, sondern dieser feste Wert "
    "als uebergaenge-Parameter von F_ARBEITSMENGE.",
)
konst(
    "boden_verdicht_leistung_m2_pro_h_uebergang",
    "800",
    "m²/(h·Übergang)",
    bez="Walzleistung je Übergang (Boden)",
    beschreibung="Walzleistung je Stunde und Übergang für die Bodenverdichtung; "
    "leistung-Parameter "
    "von F_STUNDEN, Übergangszahl aus boden_verdicht_uebergaenge. PLATZHALTER.",
)

# --- Oberboden andecken (Bankettbereich, dünn ≤5 cm, KEINE Verdichtung) — PLACEHOLDERS
# ---
konst(
    "oberboden_andeck_hand_m2_pro_h",
    "80",
    "m²/h",
    bez="Andeckleistung Kolonne (Hand)",
    beschreibung="Andeckleistung Oberboden von Hand (Kolonne) je Stunde; "
    "basisleistung-Parameter "
    "von F_LEISTUNG_ERSCHWERT (durch erschwernisfaktor geteilt), dann F_STUNDEN. "
    "PLATZHALTER.",
)
konst(
    "oberboden_andeck_grader_m2_pro_h",
    "400",
    "m²/h",
    bez="Andeckleistung Grader",
    beschreibung="Andeckleistung Oberboden mit Grader je Stunde; leistung-Parameter "
    "von F_STUNDEN "
    "für OBERBODEN_GRADER. PLATZHALTER.",
)

# --- Unterlage reinigen: sweeper vs high-pressure wash-vacuum (PLACEHOLDERS) ---
konst(
    "kehr_leistung_m2_pro_h",
    "1200",
    "m²/h",
    bez="Kehrleistung",
    beschreibung="Kehrleistung selbstaufnehmende Kehrmaschine je Stunde "
    "(Einzelflächen); "
    "leistung-Parameter von F_STUNDEN für REINIGEN_KEHREN. PLATZHALTER.",
)
konst(
    "kehrmaschine_stundensatz_eur",
    "60",
    "€/h",
    bez="Kehrmaschinenstundensatz",
    beschreibung="Gerätestundensatz Kehrmaschine inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "kehrmaschine_l_pro_h",
    "8",
    "l/h",
    beschreibung="Kraftstoffverbrauch Kehrmaschine je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "ent_kehrgut_eur_pro_m2",
    "0.05",
    "€/m²",
    bez="Entsorgung Kehrgut",
    beschreibung="Entsorgungs-/Verwertungssatz Kehrgut je m² gereinigter Fläche "
    "(leichtes Kehrgut); "
    "satz-Parameter der Kehrgut-Entsorgungszeile (F_KOSTEN_SATZ). PLATZHALTER.",
)
konst(
    "hd_reinigung_leistung_m2_pro_h",
    "1500",
    "m²/h",
    bez="HD-Reinigungsleistung",
    beschreibung="Reinigungsleistung Hochdruck-Wasch-Sauganlage je Stunde (0–6 km/h × "
    "2,30 m "
    "Arbeitsbreite); leistung-Parameter von F_STUNDEN für REINIGEN_HD. PLATZHALTER.",
)
konst(
    "hd_waschsaug_stundensatz_eur",
    "320",
    "€/h",
    bez="HD-Wasch-Sauganlagenstundensatz",
    beschreibung="Gerätestundensatz Hochdruck-Wasch-Sauganlage inkl. Wasser/Verschleiß "
    "(teuer); "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "hd_waschsaug_l_pro_h",
    "40",
    "l/h",
    beschreibung="Kraftstoffverbrauch HD-Wasch-Sauganlage je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "ent_waschschlamm_eur_pro_m2",
    "0.25",
    "€/m²",
    bez="Entsorgung Waschschlamm",
    beschreibung="Entsorgungssatz Waschschlamm je m² gereinigter Fläche; "
    "satz-Parameter der "
    "Waschschlamm-Entsorgungszeile. PLATZHALTER — je nach Belastung anpassen.",
)

# --- Anspritzen / Schichtenverbund (Rampenspritzgerät) — PLACEHOLDERS ---
konst(
    "anspritz_leistung_m2_pro_h",
    "4000",
    "m²/h",
    bez="Spritzleistung",
    beschreibung="Spritzleistung Rampenspritzgerät je Stunde (der Spritzvorgang selbst "
    "ist "
    "nebensächlich, Material dominiert); leistung-Parameter von F_STUNDEN für "
    "ANSPRITZEN. PLATZHALTER.",
)
konst(
    "spritzgeraet_stundensatz_eur",
    "90",
    "€/h",
    bez="Spritzgerätstundensatz",
    beschreibung="Gerätestundensatz Rampenspritzgerät inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "spritzgeraet_l_pro_h",
    "10",
    "l/h",
    beschreibung="Kraftstoffverbrauch Spritzgerät je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)

# --- Asphalt paving train + supporting works (PLACEHOLDERS) ---
konst(
    "asphalt_zug_geraet_eur_pro_h",
    "520",
    "€/h",
    bez="Asphaltzug-Gerätesatz (Pauschal)",
    beschreibung="Pauschaler Gerätesatz des kompletten Asphaltzugs (Fertiger + "
    "Beschicker + 2 "
    "Walzen) inkl. Verschleiß und Kraftstoff je Stunde; stundensatz-Parameter der "
    "Maschinenzeile (F_MASCHINE ohne separaten Verbrauch). PLATZHALTER.",
)
konst(
    "asphalt_kolonne",
    "6",
    "Pers.",
    bez="Asphalteinbaukolonne",
    beschreibung="Kolonnenstärke maschineller Asphalteinbau (feste Besetzung des "
    "Einbauzugs); "
    "kolonne-Parameter von F_LOHN für den Asphalteinbau.",
)
konst(
    "grid_verlege_leistung_m2_pro_h",
    "400",
    "m²/h",
    bez="Verlegeleistung Asphalteinlage",
    beschreibung="Verlegeleistung Asphalteinlage/Bewehrungsgitter durch Fachpersonal "
    "je Stunde; "
    "leistung-Parameter von F_STUNDEN für GRID_EINBAU. PLATZHALTER.",
)
konst(
    "grid_geraet_stundensatz_eur",
    "40",
    "€/h",
    bez="Verlegegerätstundensatz (Grid)",
    beschreibung="Pauschaler Gerätesatz Verlegegerät Asphalteinlage je Stunde (ohne "
    "Verbrauch); "
    "stundensatz-Parameter der Maschinenzeile.",
)
konst(
    "grid_kolonne",
    "4",
    "Pers.",
    bez="Verlegekolonne (Grid)",
    beschreibung="Kolonnenstärke Fachpersonal Asphalteinlage-Verlegung; "
    "kolonne-Parameter von F_LOHN.",
)
stammdaten_mit_default(
    "abstreukoernung_preis_eur_pro_t",
    "baustoff.basispreis_eur",
    "30",
    "€/t",
    bez="Abstreukörnungspreis",
    beschreibung="Preis Abstreukörnung (LFK 1/3) je Tonne — Baustoff-Basispreis; "
    "satz-Parameter der Abstumpfungs-Materialzeile.",
)
konst(
    "abstreuen_leistung_m2_pro_h",
    "3000",
    "m²/h",
    bez="Abstreuleistung",
    beschreibung="Maschinelle Abstreu- und Einwalzleistung je Stunde; "
    "leistung-Parameter von "
    "F_STUNDEN für ABSTUMPFEN. PLATZHALTER.",
)
konst(
    "abstreuer_stundensatz_eur",
    "75",
    "€/h",
    bez="Abstreuerstundensatz",
    beschreibung="Gerätestundensatz Abstreumaschine inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "abstreuer_l_pro_h",
    "9",
    "l/h",
    beschreibung="Kraftstoffverbrauch Abstreumaschine je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "ent_abstreu_eur_pro_m2",
    "0.05",
    "€/m²",
    bez="Entsorgung loses Abstreugut",
    beschreibung="Satz je m² für Aufnahme und Verwertung des losen Abstreuguts; "
    "satz-Parameter der "
    "Abstreugut-Entsorgungszeile. PLATZHALTER.",
)
konst(
    "naht_aufweiten_leistung_m_pro_h",
    "60",
    "m/h",
    bez="Nahtaufweitleistung",
    beschreibung="Leistung Fuge schneiden/aufweiten (25×10 mm) je laufendem Meter und "
    "Stunde; "
    "leistung-Parameter von F_STUNDEN für NAHT_AUFWEITEN. PLATZHALTER.",
)
stammdaten_mit_default(
    "fugenmasse_preis_eur_pro_t",
    "baustoff.basispreis_eur",
    "1800",
    "€/t",
    bez="Fugenmassepreis",
    beschreibung="Preis Fugenmasse N2 (heiß, inkl. Voranstrich) je Tonne — "
    "Baustoff-Basispreis; satz-Parameter der Fugenfüllungs-Materialzeile.",
)
konst(
    "fugenmasse_dichte_t_pro_m3",
    "1.10",
    "t/m³",
    bez="Dichte Fugenmasse",
    beschreibung="Rohdichte Fugenmasse; dichte-Parameter von F_MENGE_VOLUMEN, das aus "
    "dem "
    "Fugenspalt-Quadervolumen (Breite × Tiefe × Länge) die Tonnage rechnet.",
)
konst(
    "fugenfuellung_leistung_m_pro_h",
    "80",
    "m/h",
    bez="Fugenfüllleistung",
    beschreibung="Leistung Fugenfüllung je laufendem Meter und Stunde; "
    "leistung-Parameter von "
    "F_STUNDEN für FUGENFUELLUNG. PLATZHALTER.",
)
konst(
    "fugen_geraet_stundensatz_eur",
    "30",
    "€/h",
    bez="Fugengerätstundensatz",
    beschreibung="Gerätestundensatz Fugenverguss-/Applikationsgerät inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "fugen_geraet_l_pro_h",
    "3",
    "l/h",
    beschreibung="Kraftstoffverbrauch Fugengerät je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)

# --- Asphalt-Handeinbau (Kleinflächen): langsame Kolonne + kleine Walze (PLACEHOLDERS)
# ---
konst(
    "handeinbau_leistung_m2_pro_h",
    "40",
    "m²/h",
    bez="Handeinbauleistung",
    beschreibung="Einbauleistung Asphalt-Handkolonne für Kleinflächen je Stunde "
    "(langsam); "
    "leistung-Parameter von F_STUNDEN für ASPHALT_HAND. PLATZHALTER.",
)
konst(
    "handeinbau_kolonne",
    "5",
    "Pers.",
    bez="Handeinbaukolonne",
    beschreibung="Kolonnenstärke Asphalt-Handeinbau; kolonne-Parameter von F_LOHN.",
)

# --- Gussasphalt (MA, fließfähig, KEINE Verdichtung; Abstreuen separat) — PLACEHOLDERS
# ---
stammdaten_mit_default(
    "gussasphalt_preis_eur_pro_t",
    "baustoff.basispreis_eur",
    "120.00",
    "€/t",
    bez="Gussasphaltpreis",
    beschreibung="Preis Gussasphaltmischgut (MA) je Tonne — Baustoff-Basispreis, "
    "Default MA 8 S; satz-Parameter der Gussasphalt-Materialzeile.",
)
konst(
    "gussasphalt_leistung_m2_pro_h",
    "80",
    "m²/h",
    bez="Gussasphalt-Einbauleistung",
    beschreibung="Einbauleistung Gussasphalt (Bohle/Kübel, keine Walzverdichtung) je "
    "Stunde; "
    "leistung-Parameter von F_STUNDEN für GUSSASPHALT. PLATZHALTER.",
)
konst(
    "gussasphalt_geraet_stundensatz_eur",
    "150",
    "€/h",
    bez="Gussasphaltgerätstundensatz",
    beschreibung="Gerätestundensatz Gussasphaltfertiger/Kocher inkl. Verschleiß; "
    "F_MASCHINE-"
    "stundensatz-Default.",
)
konst(
    "gussasphalt_l_pro_h",
    "15",
    "l/h",
    beschreibung="Kraftstoffverbrauch Gussasphaltgerät je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "gussasphalt_kolonne",
    "5",
    "Pers.",
    bez="Gussasphaltkolonne",
    beschreibung="Kolonnenstärke Gussasphalteinbau; kolonne-Parameter von F_LOHN.",
)

# --- DSK (Dünnschichtbelag im Kalteinbau / Slurry): Material je m², schnelle Maschine —
# PLACEHOLDERS ---
stammdaten_mit_default(
    "dsk_material_eur_pro_m2",
    "baustoff.basispreis_eur",
    "4.50",
    "€/m²",
    bez="DSK-Materialpreis je m²",
    beschreibung="Preis DSK-/Slurry-Mischgut je m² (nicht je Tonne!) — Baustoff-"
    "Basispreis; satz-Parameter der DSK-Materialzeile (F_KOSTEN_SATZ "
    "direkt über die Fläche).",
)
konst(
    "dsk_leistung_m2_pro_h",
    "2000",
    "m²/h",
    bez="DSK-Einbauleistung",
    beschreibung="Einbauleistung DSK-/Slurry-Fertiger je Stunde; leistung-Parameter "
    "von F_STUNDEN "
    "für DSK. PLATZHALTER.",
)
konst(
    "dsk_geraet_stundensatz_eur",
    "180",
    "€/h",
    bez="DSK-Fertigerstundensatz",
    beschreibung="Gerätestundensatz DSK-Fertiger inkl. Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "dsk_l_pro_h",
    "20",
    "l/h",
    beschreibung="Kraftstoffverbrauch DSK-Fertiger je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)
konst(
    "dsk_kolonne",
    "4",
    "Pers.",
    bez="DSK-Kolonne",
    beschreibung="Kolonnenstärke DSK-Einbau; kolonne-Parameter von F_LOHN.",
)

# --- Randabdichtung/Nahtabdichtung: Dichtband/-masse je m, kleine Kolonne + Gerät —
# PLACEHOLDERS ---
stammdaten_mit_default(
    "randabdichtung_material_eur_pro_m",
    "baustoff.basispreis_eur",
    "3.00",
    "€/m",
    bez="Randabdichtungsmaterialpreis je m",
    beschreibung="Preis Fugenband/Randabdichtmasse je laufendem Meter — Baustoff-"
    "Basispreis; satz-Parameter der Randabdichtungs-Materialzeile.",
)
konst(
    "randabdichtung_leistung_m_pro_h",
    "60",
    "m/h",
    bez="Randabdichtungsleistung",
    beschreibung="Abdichtleistung (Reinigen + Anbringen) je laufendem Meter und "
    "Stunde; "
    "leistung-Parameter von F_STUNDEN für RANDABDICHTUNG. PLATZHALTER.",
)
konst(
    "randabdichtung_geraet_stundensatz_eur",
    "20",
    "€/h",
    bez="Randabdichtungsgerätstundensatz",
    beschreibung="Gerätestundensatz Applikator/Heizgerät Randabdichtung inkl. "
    "Verschleiß; "
    "F_MASCHINE-stundensatz-Default.",
)
konst(
    "randabdichtung_l_pro_h",
    "2",
    "l/h",
    beschreibung="Kraftstoffverbrauch Applikator/Heizgerät je Betriebsstunde; "
    "F_MASCHINE-verbrauch-Default.",
)

# --- master-data bridges (pull from the chosen Baustoff) ---
stammdaten(
    "dichte_t_pro_m3",
    "baustoff.rohdichte_t_pro_m3",
    "t/m³",
    bez="Rohdichte Baustoff",
    beschreibung="Rohdichte des gewählten Baustoffs (Brücke auf "
    "baustoff.rohdichte_t_pro_m3); "
    "dichte-Parameter von F_MENGE_VOLUMEN für die Schüttgut-/Abtragstonnage.",
)
stammdaten(
    "verdichtungsfaktor",
    "baustoff.verdichtungsfaktor",
    "-",
    bez="Verdichtungsfaktor",
    beschreibung="Auflockerungs-/Verdichtungsfaktor des gewählten Baustoffs (Brücke "
    "auf "
    "baustoff.verdichtungsfaktor); verdichtungsfaktor-Parameter von F_MENGE_VOLUMEN "
    "beim Einbau (Liefermenge > Einbauvolumen).",
)
# Generic per-t material price (unbound aggregates, bitumen emulsion) + the
# Asphalteinlage product price: both now come from the selected Baustoff's per-Einheit
# basispreis (a per- position kontext value still overrides; unresolved -> HITL).
stammdaten(
    "materialpreis_eur_pro_t",
    "baustoff.basispreis_eur",
    "€/t",
    bez="Materialpreis (generisch)",
    beschreibung="Preis je Tonne des gewählten Baustoffs (Brücke auf "
    "baustoff.basispreis_eur) — "
    "für Mineralgemische, Boden, Bitumenemulsion; satz-Parameter der Material-/"
    "Antransportzeilen. Eine Position kann ihn per kontext überschreiben.",
)
stammdaten(
    "grid_preis_eur_pro_m2",
    "baustoff.basispreis_eur",
    "€/m²",
    bez="Preis Asphalteinlage je m²",
    beschreibung="Preis Asphalteinlage/Bewehrungsgitter je m² (Brücke auf "
    "baustoff.basispreis_eur "
    "des Gitter-Produkts); satz-Parameter der Grid-Materialzeile über die Fläche.",
)
