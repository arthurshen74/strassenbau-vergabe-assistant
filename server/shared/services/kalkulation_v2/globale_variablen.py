"""Registry of project-scoped global context variables.

Each `GlobaleVariable` is resolved once per project (RAG + synthesis, then user
confirmation) and reused by every LV position calculation. `ziel_variable` names the
engine variable a global sources (e.g. `strip_length_m` -> `laenge_m`); location globals
carry no engine variable (their coords drive supplier ranking / deponie routing instead).
`entfernung_deponie_km` is a derived, governed variable (computed by routing), not a
member of this registry.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.services.kalkulation_v2.model import Datentyp

# Variable-name contract values (the `variable_name` column, API schema fields, graph state).
VAR_BAUSTELLE_LOCATION = "baustelle_location"
VAR_DEPONIE_LOCATION = "deponie_location"
VAR_STRIP_LENGTH_M = "strip_length_m"
VAR_STRIP_WIDTH_M = "strip_width_m"
VAR_FRAESGUT_KLASSE = "fraesgut_klasse"

# Derived governed variable: routed Baustelle -> Deponie distance. Computed, not resolved.
VAR_ENTFERNUNG_DEPONIE_KM = "entfernung_deponie_km"

# Engine variables the strip/fraesgut globals source.
ZIEL_LAENGE_M = "laenge_m"
ZIEL_FLAECHE_M2 = "flaeche_m2"  # bridged from strip_length_m x strip_width_m (fallback geometry)
ZIEL_FRAESGUT_KLASSE = "fraesgut_klasse"


class GlobaleVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    bezeichnung: str
    einheit: str | None
    datentyp: Datentyp
    ist_standort: bool = False  # location: string value + geocoded coords
    ziel_variable: str | None = None  # engine variable it sources, if any
    rag_prompt: str  # retrieval intent for retrieve_context


GLOBALE_VARIABLEN: dict[str, GlobaleVariable] = {
    VAR_BAUSTELLE_LOCATION: GlobaleVariable(
        name=VAR_BAUSTELLE_LOCATION,
        bezeichnung="Standort der Baustelle",
        einheit=None,
        datentyp=Datentyp.DEZIMAL,
        ist_standort=True,
        rag_prompt=(
            "Wo befindet sich die Baustelle? Ort, Adresse, Straße, Streckenabschnitt "
            "oder Bauabschnitt der Maßnahme."
        ),
    ),
    VAR_DEPONIE_LOCATION: GlobaleVariable(
        name=VAR_DEPONIE_LOCATION,
        bezeichnung="Standort der Deponie / Entsorgung",
        einheit=None,
        datentyp=Datentyp.DEZIMAL,
        ist_standort=True,
        rag_prompt=(
            "Wohin wird der Abtrag bzw. das Fräsgut transportiert und entsorgt? "
            "Deponie, Entsorgungsanlage oder Wiederverwertungsanlage."
        ),
    ),
    VAR_STRIP_LENGTH_M: GlobaleVariable(
        name=VAR_STRIP_LENGTH_M,
        bezeichnung="Länge des Streckenabschnitts",
        einheit="m",
        datentyp=Datentyp.DEZIMAL,
        ziel_variable=ZIEL_LAENGE_M,
        rag_prompt=(
            "Wie lang ist der Streckenabschnitt bzw. die Baustrecke in Metern? "
            "Gesamtlänge der zu bearbeitenden Strecke."
        ),
    ),
    VAR_STRIP_WIDTH_M: GlobaleVariable(
        name=VAR_STRIP_WIDTH_M,
        bezeichnung="Breite des Streckenabschnitts",
        einheit="m",
        datentyp=Datentyp.DEZIMAL,
        rag_prompt=(
            "Wie breit ist die Fahrbahn bzw. der Streckenabschnitt in Metern? "
            "Arbeitsbreite der zu bearbeitenden Fläche."
        ),
    ),
    VAR_FRAESGUT_KLASSE: GlobaleVariable(
        name=VAR_FRAESGUT_KLASSE,
        bezeichnung="Fräsgutklasse",
        einheit=None,
        datentyp=Datentyp.GANZZAHL,
        ziel_variable=ZIEL_FRAESGUT_KLASSE,
        rag_prompt=(
            "Welche Fräsgutklasse bzw. Belastungsklasse hat der Asphalt? "
            "Unbelastet, pechhaltig oder teerhaltig (Klasse 1 bis 3)."
        ),
    ),
}

GLOBAL_VAR_NAMES = frozenset(GLOBALE_VARIABLEN)
