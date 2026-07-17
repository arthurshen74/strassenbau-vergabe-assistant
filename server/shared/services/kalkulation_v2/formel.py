"""
formel.py — the base formula catalog (~16 parameterized DSL expressions).

Every calculation in the Katalog is an INSTANTIATION of one of these base formulas
(REZEPT_REDESIGN_PLAN.md Appendix A): a Vorgang binds the declared parameters to source
paths; the expressions themselves are written once, in canonical units (m, m², m³, t, h,
€, St, l, km). Unit scaling happens at the binding seam (`einheiten.py`), never inside
an expression — no `/100`, `/1000` arithmetic here.

Kurven- und Selektionsformeln (F_LEISTUNG_TIEFE, F_UEBERGAENGE, F_STAFFEL) carry the
empirical company knowledge as PARAMETERS; the expressions are just the shapes.

Exports FORMELN (name -> Formel). Import-time validation guards the catalog.
"""

from decimal import Decimal

from shared.services.kalkulation_v2.model import Formel, FormelParameter as P

FORMELN: dict[str, Formel] = {}


def _basis(
    name: str, ausdruck: str, einheit: str | None, beschreibung: str, parameter: list[P]
) -> None:
    f = Formel(
        name=name,
        ausdruck=ausdruck,
        einheit=einheit,
        beschreibung=beschreibung,
        parameter=parameter,
    )
    probleme = f.validieren()
    if probleme:
        raise ValueError(f"Basisformel {name}: {probleme}")
    FORMELN[name] = f


# --------------------------------------------------------------------------- #
# Mengengerüst — Geometrie und Masse
# --------------------------------------------------------------------------- #
_basis(
    "F_MENGE_VOLUMEN",
    "volumen * dichte * verdichtungsfaktor",
    "t",
    "Masse aus Volumen und Rohdichte, optional mit Verdichtungsfaktor für verdichteten "
    "Einbau (Liefermenge > Einbauvolumen). Der universelle m³→t-Übergang: für Abtrag "
    "ohne "
    "Verdichtung den Faktor ungebunden lassen (Standard 1).",
    [
        P(
            name="volumen",
            einheit="m3",
            beschreibung="Das Volumen in m³: die gebuchte Geometrie "
            "(kontext.volumen_m3) oder "
            "eine Volumen-Instanz (formel.volumen).",
        ),
        P(
            name="dichte",
            einheit="t/m3",
            beschreibung="Rohdichte des Materials: baustoff.rohdichte_t_pro_m3 des "
            "gebundenen "
            "Baustoffs, sonst ein Stammdaten-Satz (z. B. dichte_asphalt_t_pro_m3).",
        ),
        P(
            name="verdichtungsfaktor",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Auflockerungs-/Verdichtungszuschlag: "
            "baustoff.verdichtungsfaktor beim "
            "Einbau; ungebunden (1) bei Abtrag und Entsorgungsmengen.",
        ),
    ],
)
_basis(
    "F_VOLUMEN_FLAECHE",
    "flaeche * dicke",
    "m3",
    "Volumen aus Fläche und Schicht-/Einbaudicke. Der m²→m³-Übergang für flächig "
    "gebuchte "
    "Leistungen mit Dickenangabe (Fräsen, Asphalt-Einbau, Bodenabtrag).",
    [
        P(
            name="flaeche",
            einheit="m2",
            beschreibung="Die Fläche in m²: die gebuchte Geometrie "
            "(kontext.flaeche_m2) oder "
            "eine Flächen-Instanz.",
        ),
        P(
            name="dicke",
            einheit="m",
            beschreibung="Dicke bzw. Tiefe in m; cm-Quellen (kontext.tiefe_cm, "
            "kontext.einbaudicke_cm) skaliert der Konverter.",
        ),
    ],
)
_basis(
    "F_FLAECHE_VOLUMEN",
    "volumen / dicke",
    "m2",
    "Fläche aus Volumen und Schichtdicke — die Umkehrbrücke für m³-gebuchte "
    "Leistungen, "
    "deren Arbeitsschritte flächenbezogen sind (FSS profilieren/verdichten).",
    [
        P(
            name="volumen",
            einheit="m3",
            beschreibung="Das gebuchte Volumen (kontext.volumen_m3).",
        ),
        P(
            name="dicke",
            einheit="m",
            beschreibung="Schichtdicke in m (kontext.schichtdicke_m; cm-Quellen "
            "skaliert "
            "der Konverter).",
        ),
    ],
)
_basis(
    "F_VOLUMEN_QUADER",
    "breite * laenge * tiefe",
    "m3",
    "Quadervolumen aus drei Kantenmaßen — Streckengeometrie (Breite × Länge × Tiefe) "
    "und "
    "Querschnittsmengen (Fugenspalt: Breite × Tiefe × Länge).",
    [
        P(
            name="breite",
            einheit="m",
            beschreibung="Breite in m; mm/cm skaliert der Konverter.",
        ),
        P(name="laenge", einheit="m", beschreibung="Länge in m (kontext.laenge_m)."),
        P(
            name="tiefe",
            einheit="m",
            beschreibung="Tiefe/Dicke in m; mm/cm skaliert der Konverter.",
        ),
    ],
)
_basis(
    "F_MENGE_ANSATZ",
    "ansatz * bezugsmenge",
    "t",
    "Menge aus einem Ansatz (Rate je Bezugseinheit) mal Bezugsmenge: kg/m² × Fläche, "
    "kg/m × Länge, t/t × Tonnage. Der Ansatz trägt seine Einheit; der Konverter "
    "normalisiert kg→t exakt.",
    [
        P(
            name="ansatz",
            einheit=None,
            beschreibung="Der Ansatz (z. B. Abstreumenge kg/m², Vergussmasse kg/m, "
            "Fräsgut-Anteil t/t): eine Stammdaten- oder Kontext-Variable.",
        ),
        P(
            name="bezugsmenge",
            einheit=None,
            beschreibung="Die Bezugsmenge in der Bezugseinheit des Ansatzes (Fläche, "
            "Länge, "
            "Stück oder Tonnage).",
        ),
    ],
)
_basis(
    "F_ARBEITSMENGE",
    "basismenge * lagen * uebergaenge",
    None,
    "Arbeitsmenge bei mehrlagigem/mehrgängigem Arbeiten: Basismenge × Lagen × "
    "Übergänge. "
    "Beide Faktoren ungebunden lassen (1), wenn einlagig bzw. eingängig gearbeitet "
    "wird.",
    [
        P(
            name="basismenge",
            einheit=None,
            beschreibung="Die Basismenge (meist die Fläche einer Lage).",
        ),
        P(
            name="lagen",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Anzahl Einbaulagen (formel.lagen aus F_LAGEN).",
        ),
        P(
            name="uebergaenge",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Anzahl Arbeitsgänge je Lage, z. B. Walzübergänge "
            "(formel.uebergaenge "
            "aus F_UEBERGAENGE oder ein Stammdaten-Satz).",
        ),
    ],
)
_basis(
    "F_LAGEN",
    "ceil(dicke / max_lagendicke)",
    "-",
    "Anzahl Einbaulagen: Schichtdicke geteilt durch die maximal verdichtbare "
    "Lagendicke, "
    "aufgerundet. Die max. Lagendicke ist Material-/Normwissen, kein Formelwissen.",
    [
        P(
            name="dicke",
            einheit="m",
            beschreibung="Gesamte Schichtdicke in m (kontext.schichtdicke_m).",
        ),
        P(
            name="max_lagendicke",
            einheit="m",
            beschreibung="Maximale Lagendicke des Materials (Stammdaten-Satz, z. B. "
            "max_lagendicke_b2_m).",
        ),
    ],
)

# --------------------------------------------------------------------------- # Zeit und
# Kosten --------------------------------------------------------------------------- #
_basis(
    "F_STUNDEN",
    "menge / leistung",
    "h",
    "Arbeitsdauer eines Vorgangs aus Arbeitsmenge und Leistungsansatz. Universell "
    "für jeden mengenproportionalen Vorgang: Fräsen (m²), Schneiden (m), Aushub "
    "(m³), Asphalteinbau (t), Schieberkappen (St). Mengeneinheit und Bezugseinheit "
    "des Leistungsansatzes müssen dimensionsgleich sein; für Dimensionssprünge eine "
    "Mengengerüst-Formel vorschalten.",
    [
        P(
            name="menge",
            einheit=None,
            beschreibung="Die Arbeitsmenge in der Bezugsgröße der Leistung: die "
            "gebuchte "
            "Geometrie-Variable der LV-Position (m² → kontext.flaeche_m2, m → "
            "kontext.laenge_m, m³ → kontext.volumen_m3, t → kontext.menge_t, "
            "St → kontext.anzahl_st) oder eine Mengen-Instanz (formel.arbeitsmenge).",
        ),
        P(
            name="leistung",
            einheit=None,
            beschreibung="Der Leistungsansatz (Menge je Stunde): das Leistungsprofil "
            "der "
            "gebundenen Maschine (überschreibt die Instanz), eine Kurve "
            "(formel.leistung aus F_LEISTUNG_TIEFE) oder ein Stammdaten-Ansatz. "
            "Niemals als Zahl in einen Ausdruck schreiben.",
        ),
    ],
)
_basis(
    "F_LOHN",
    "stunden * stundenlohn * kolonne * anteil",
    "€",
    "Lohnkosten: Arbeitsdauer × Mittellohn × Kolonnenstärke. Der Anteil skaliert "
    "Teiltätigkeiten eines kombinierten Vorgangs (z. B. Thermo-Phasen).",
    [
        P(
            name="stunden",
            einheit="h",
            beschreibung="Die Arbeitsdauer des Vorgangs (formel.arbeitszeit aus "
            "F_STUNDEN).",
        ),
        P(
            name="stundenlohn",
            einheit="€/h",
            beschreibung="Kalkulatorischer Mittellohn je gewerblichem Mitarbeiter "
            "(stammdaten.stundenlohn_eur).",
        ),
        P(
            name="kolonne",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Kolonnenstärke: kontext.anzahl_arbeiter (situativ, je "
            "Position "
            "geprüft), ein fester Kolonnen-Satz oder ungebunden (1 Bediener).",
        ),
        P(
            name="anteil",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Zeitanteil dieser Teiltätigkeit an den Vorgangsstunden "
            "(0–1); "
            "ungebunden = voller Vorgang.",
        ),
    ],
)
_basis(
    "F_MASCHINE",
    "stunden * (stundensatz + verbrauch * kraftstoffpreis) * anteil",
    "€",
    "Maschinenkosten: Arbeitsdauer × (Gerätestundensatz + Kraftstoffkosten je Stunde). "
    "Satz und Verbrauch kommen aus dem Eigenschafts-Beutel der gebundenen Maschine "
    "(kosten_bindung überschreibt die Stammdaten-Sätze); ohne Verbrauchsangabe (0) "
    "bleibt "
    "der reine Gerätesatz. Je gleichzeitig laufender Maschine eine eigene Kostenzeile.",
    [
        P(
            name="stunden",
            einheit="h",
            beschreibung="Die Arbeitsdauer des Vorgangs (formel.arbeitszeit).",
        ),
        P(
            name="stundensatz",
            einheit="€/h",
            beschreibung="Gerätestundensatz inkl. Verschleiß: Stammdaten-Satz als "
            "Vorgabe "
            "(z. B. stammdaten.kaltfraese_stundensatz_eur); eine gebundene "
            "Maschine überschreibt ihn aus ihrem Eigenschafts-Beutel.",
        ),
        P(
            name="verbrauch",
            einheit="l/h",
            standard=Decimal("0"),
            beschreibung="Kraftstoffverbrauch: Stammdaten-Satz als Vorgabe, von der "
            "Maschine "
            "überschrieben; ungebunden (0) bei Pauschalsätzen.",
        ),
        P(
            name="kraftstoffpreis",
            einheit="€/l",
            standard=Decimal("0"),
            beschreibung="Kraftstoffpreis (stammdaten.kraftstoffpreis_eur_pro_l).",
        ),
        P(
            name="anteil",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Zeitanteil dieser Maschine an den Vorgangsstunden (0–1).",
        ),
    ],
)
_basis(
    "F_KOSTEN_SATZ",
    "menge * satz",
    "€",
    "Kosten aus Menge × Satz — die universelle Satzanwendung: Materialkosten (t × €/t, "
    "m² × €/m², St × €/St), Entsorgung (t × €/t), Zulagen (m × €/m). Mengeneinheit und "
    "Satz-Bezugseinheit müssen zueinander passen.",
    [
        P(
            name="menge",
            einheit=None,
            beschreibung="Die abzurechnende Menge: gebuchte Geometrie oder "
            "Mengen-Instanz "
            "(formel.menge, formel.tonnage).",
        ),
        P(
            name="satz",
            einheit=None,
            beschreibung="Der Satz je Bezugseinheit: Lieferantenpreis, Stammdaten-Satz "
            "oder "
            "eine Staffel-Instanz (formel.entsorgungssatz aus F_STAFFEL).",
        ),
    ],
)
_basis(
    "F_TRANSPORT",
    "menge * satz * entfernung",
    "€",
    "Transportkosten: Tonnage × Frachtsatz × Entfernung. Antransport rechnet mit der "
    "Lieferanten-Entfernung, Abtransport mit der Deponie-Entfernung.",
    [
        P(
            name="menge",
            einheit="t",
            beschreibung="Die transportierte Tonnage (formel.tonnage oder "
            "kontext.menge_t).",
        ),
        P(
            name="satz",
            einheit="€/(t·km)",
            beschreibung="Frachtsatz (stammdaten.transport_eur_pro_t_km).",
        ),
        P(
            name="entfernung",
            einheit="km",
            beschreibung="Entfernung: kontext.entfernung_lieferant_km (Antransport) "
            "bzw. "
            "kontext.entfernung_deponie_km (Abtransport/Entsorgung).",
        ),
    ],
)

# --------------------------------------------------------------------------- # Kurven
# und Selektionen — Parameter sind Firmenwissen
# --------------------------------------------------------------------------- #
_basis(
    "F_LEISTUNG_TIEFE",
    "max(untergrenze, min(obergrenze, tiefenkonstante / tiefe)) / erschwernisfaktor",
    None,
    "Tiefenabhängige Produktivität: hyperbolisch fallend mit der Arbeitstiefe, "
    "begrenzt "
    "durch Unter-/Obergrenze, geteilt durch den Erschwernisfaktor. Die Parameter sind "
    "empirisches Geräte-/Firmenwissen (Fräsen, Schneiden, Aufbrechen) — kalibrieren, "
    "nicht kopieren.",
    [
        P(
            name="tiefenkonstante",
            einheit=None,
            beschreibung="Die Tiefenkonstante k (Leistung × Tiefe): bei k=10 m·m²/h "
            "sind es "
            "250 m²/h bei 4 cm. Empirischer Geräteparameter.",
        ),
        P(
            name="tiefe",
            einheit="m",
            beschreibung="Arbeits-/Frästiefe in m (kontext.tiefe_cm; der Konverter "
            "skaliert cm→m).",
        ),
        P(
            name="untergrenze",
            einheit=None,
            standard=Decimal("0"),
            beschreibung="Mindestleistung, unter die das Gerät auch bei großer Tiefe "
            "nicht "
            "fällt (Prozessminimum).",
        ),
        P(
            name="obergrenze",
            einheit=None,
            standard=Decimal("1000000000"),
            beschreibung="Leistungsdeckel bei geringer Tiefe (Präzisionsarbeit, z. B. "
            "Feinfräsen); ungebunden = kein Deckel.",
        ),
        P(
            name="erschwernisfaktor",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Erschwernis der Baustelle (kontext.erschwernisfaktor): "
            "Kleinflächen, "
            "Handarbeit, beengte Verhältnisse.",
        ),
    ],
)
_basis(
    "F_LEISTUNG_ERSCHWERT",
    "basisleistung / erschwernisfaktor",
    None,
    "Konstante Basisproduktivität, geteilt durch den Erschwernisfaktor — für Vorgänge "
    "ohne "
    "Tiefenabhängigkeit, deren Tempo unter erschwerten Bedingungen sinkt (Handarbeit).",
    [
        P(
            name="basisleistung",
            einheit=None,
            beschreibung="Basisleistung unter Normalbedingungen (Stammdaten-Ansatz).",
        ),
        P(
            name="erschwernisfaktor",
            einheit="-",
            standard=Decimal("1"),
            beschreibung="Erschwernis der Baustelle (kontext.erschwernisfaktor).",
        ),
    ],
)
_basis(
    "F_UEBERGAENGE",
    "ceil(y0 + (max(x0, min(x1, x)) - x0) * (y1 - y0) / (x1 - x0))",
    "-",
    "Geklemmte lineare Interpolation, aufgerundet: Arbeitsgänge aus einem Zielwert "
    "zwischen "
    "zwei Ankerpunkten (x0,y0)–(x1,y1). Der Standardfall sind Walzübergänge aus dem "
    "Ev2-Verdichtungsziel; die Anker sind Verdichtungs-Firmenwissen.",
    [
        P(
            name="x",
            einheit=None,
            beschreibung="Der Zielwert, z. B. das geforderte Ev2 (kontext.ev2_ziel).",
        ),
        P(
            name="x0",
            einheit=None,
            beschreibung="Unterer Anker-x (z. B. stammdaten.ev2_anker_min).",
        ),
        P(
            name="y0",
            einheit=None,
            beschreibung="Arbeitsgänge am unteren Anker (z. B. "
            "stammdaten.verdicht_uebergaenge_ev45).",
        ),
        P(
            name="x1",
            einheit=None,
            beschreibung="Oberer Anker-x (z. B. stammdaten.ev2_anker_max).",
        ),
        P(
            name="y1",
            einheit=None,
            beschreibung="Arbeitsgänge am oberen Anker (z. B. "
            "stammdaten.verdicht_uebergaenge_ev100).",
        ),
    ],
)
_basis(
    "F_STAFFEL",
    "satz1 if wert <= stufe1 else (satz2 if wert <= stufe2 else satz3)",
    None,
    "Dreistufige Satz-Staffel: wählt einen Satz nach einem Klassifikationswert. Der "
    "Standardfall ist der Entsorgungssatz nach Fräsgut-Belastungsklasse (≤1 "
    "verwertbar, "
    "≤2 belastet, sonst pech-/teerhaltig). Stufen und Sätze sind regulatorisches "
    "Wissen — "
    "niemals eine Klasse annehmen, der Satzunterschied ist erheblich.",
    [
        P(
            name="wert",
            einheit=None,
            beschreibung="Der Klassifikationswert (kontext.fraesgut_klasse).",
        ),
        P(name="stufe1", einheit=None, beschreibung="Obergrenze der ersten Stufe."),
        P(
            name="satz1",
            einheit=None,
            beschreibung="Satz der ersten Stufe (z. B. "
            "stammdaten.ent_fraesgut_verwertbar).",
        ),
        P(name="stufe2", einheit=None, beschreibung="Obergrenze der zweiten Stufe."),
        P(
            name="satz2",
            einheit=None,
            beschreibung="Satz der zweiten Stufe (z. B. "
            "stammdaten.ent_fraesgut_belastet).",
        ),
        P(
            name="satz3",
            einheit=None,
            beschreibung="Satz oberhalb der zweiten Stufe (z. B. "
            "stammdaten.ent_fraesgut_pechhaltig).",
        ),
    ],
)
