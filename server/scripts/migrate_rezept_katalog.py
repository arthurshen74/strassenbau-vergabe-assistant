"""One-shot cutover migration to the base-formula system (REZEPT_REDESIGN_PLAN §6, Phase
2).

Transforms the ACTIVE catalog from the old formula system (one formula per cost
variable, FORMEL-gruppe variables) into the redesigned one: 16 base formulas,
per-Vorgang `rechnung` instantiations, kontext geometry placeholders for
flaeche_m2/menge_t. Everything runs in ONE
transaction:

1. verify the pre-state — every active Vorgang/Formel is either an untouched seed row
(the new
   fixture already carries its transformation) or matches the recorded agent-authored
   corpus verbatim; anything else means the catalog drifted past this script's spec →
   hard abort;
2. retire the old formula corpus (all 174 rows), every FORMEL-gruppe variable, and the
shadowed
   stammdaten KONSTANTE `entsorgung_fraesasphalt_eur_pro_t` (replaced by F_STAFFEL
   instanzen);
3. draft the cutover bundle (base formulas from `formel.py`, the 36 fixture Rechnungen
from
   `vorgaenge.py`, the 8 agent Rechnungen authored below per Appendix B, the two kontext
   geometry placeholders), validate it with `pruefe_bundle`, activate it, bump the
   Stand;
4. smoke-load the migrated catalog through the provider (shape gate) and emit the
variable
   disposition report (Appendix C review) to eval/parity/variablen_disposition.md.

The hard activation gate runs OUTSIDE this script: `ekt_snapshot --vergleich` against
the old-engine baseline must be cent-identical before the migrated DB is trusted.

    uv run python -m scripts.migrate_rezept_katalog [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Table, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

import shared.db.tables  # noqa: F401
from shared.config import settings
from shared.db.tables.katalog_formeln import katalog_formeln
from shared.db.tables.katalog_variablen import katalog_variablen
from shared.db.unit_of_work import unit_of_work
from shared.models.katalog import (
    BundleVariable,
    BundleVorgang,
    KatalogBundle,
    KatalogEntitaet,
    KatalogStatus,
    VariablenGruppe,
)
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository
from shared.services.katalog.validierung import lade_stand, pruefe_bundle
from shared.services.kalkulation_v2.formel import FORMELN
from shared.services.kalkulation_v2.kontext_variablen import KONTEXT_VARIABLEN
from shared.services.kalkulation_v2.model import (
    FormelInstanz,
    Kostenart as KA,
    VariableDefinition,
    VorgangRechnung,
)
from shared.services.kalkulation_v2.stammdaten import STAMMDATEN_VARIABLEN
from shared.services.kalkulation_v2.provider import lade_katalog
from shared.services.kalkulation_v2.vorgaenge import VORGAENGE

BENUTZER = "migration_rezept"
BERICHT_PFAD = (
    Path(__file__).resolve().parents[2] / "eval" / "parity" / "variablen_disposition.md"
)

# The agent-authored ("kalkulator") formula corpus at Katalog-Stand 11, verbatim. The
# transformations below encode exactly these expressions — a mismatch means the live
# catalog moved past this script's spec and the mapping must be re-derived, not silently
# applied.
AGENT_FORMELN: dict[str, str] = {
    "riss_sanierung_stunden": "laenge_m / riss_sanierung_leistung_m_pro_h",
    "riss_vergussmasse_t": "laenge_m * riss_vergussmasse_kg_pro_m / 1000",
    "mk_riss_auffraesen": "riss_sanierung_stunden * (schneider_stundensatz_eur + "
    "schneider_l_pro_h * kraftstoffpreis_eur_pro_l)",
    "mk_riss_verguss_geraet": "riss_sanierung_stunden * (fugen_geraet_stundensatz_eur "
    "+ fugen_geraet_l_pro_h * kraftstoffpreis_eur_pro_l)",
    "mk_riss_verguss_material": "riss_vergussmasse_t * fugenmasse_preis_eur_pro_t + "
    "laenge_m * voranstrich_pauschal_eur_pro_m",
    "lohn_riss_auffraesen": "riss_sanierung_stunden * stundenlohn_eur * "
    "anzahl_arbeiter",
    "lohn_riss_verguss": "riss_sanierung_stunden * stundenlohn_eur * anzahl_arbeiter",
    "schieberkappen_stunden": "anzahl_st / schieberkappen_pro_h",
    "mat_schieberkappe_reg": "anzahl_st * moertel_kleinmaterial_eur_pro_st",
    "lohn_schieberkappe_reg": "schieberkappen_stunden * stundenlohn_eur * "
    "anzahl_arbeiter",
    "thermo_stunden": "menge_t / thermo_leistung_t_pro_h",
    "mat_thermo_emulsion": "menge_t * emulsion_anteil_eur_pro_t",
    "mat_thermo_asphalt": "menge_t * asphalt_preis_eur_pro_t",
    "mk_thermo_anspritzen": "thermo_stunden * anteil_anspritzen * "
    "(spritzgeraet_stundensatz_eur + spritzgeraet_l_pro_h * "
    "kraftstoffpreis_eur_pro_l)",
    "mk_thermo_ausschneiden": "thermo_stunden * anteil_ausschneiden_fraesen * "
    "(schneider_stundensatz_eur + schneider_l_pro_h * kraftstoffpreis_eur_pro_l)",
    "mk_thermo_container": "thermo_stunden * thermo_container_geraetekosten_eur_pro_h",
    "lohn_thermo_anspritzen": "thermo_stunden * anteil_anspritzen * stundenlohn_eur * "
    "anzahl_arbeiter",
    "lohn_thermo_ausschneiden": "thermo_stunden * anteil_ausschneiden_fraesen * "
    "stundenlohn_eur * anzahl_arbeiter",
    "lohn_thermo_saeubern": "thermo_stunden * anteil_saeubern * stundenlohn_eur * "
    "anzahl_arbeiter",
    "lohn_thermo_einbau": "thermo_stunden * stundenlohn_eur * anzahl_arbeiter",
    "ent_thermo_fraesgut": "menge_t * fraesgut_anteil_t_pro_t_einbau * "
    "entsorgung_fraesasphalt_eur_pro_t",
    "trans_thermo_fraesgut": "menge_t * fraesgut_anteil_t_pro_t_einbau * "
    "transport_eur_pro_t_km * entfernung_deponie_km",
    "tiefbord_stunden": "laenge_m / tiefbord_leistung_m_pro_h",
    "tiefbord_leistung_m_pro_h": "25",
    "tonnage_tiefbord_aufbruch": "laenge_m * 0.06",
    "mk_tiefbord_aufn": "tiefbord_stunden * bagger_stundensatz_eur",
    "lohn_tiefbord_aufn": "tiefbord_stunden * stundenlohn_eur * anzahl_arbeiter",
    "ent_tiefbord_aufbruch": "tonnage_tiefbord_aufbruch * "
    "entsorgung_betonaufbruch_eur_pro_t",
    "trans_tiefbord_aufbruch": "tonnage_tiefbord_aufbruch * transport_eur_pro_t_km * "
    "entfernung_deponie_km",
    # orphan, retires
    "calc_volumen_m3": "strip_width_m * strip_length_m * (strip_depth_cm / 100)",
}

# Prose for the DB-only variables the katalog agent minted for the 8 agent recipes
# (thermo / riss / tiefbord / schieberkappen) plus the project-context strip geometry —
# they live only in the live DB (not in the fixtures), so Phase 3 authors their
# beschreibung here and supersedes them with it. Values/cascade are read from the active
# row; only beschreibung is added (parity-neutral).
DB_ONLY_VARIABLEN_PROSA: dict[str, str] = {
    "riss_sanierung_leistung_m_pro_h": "Sanierungsleistung Rissverguss/-auffräsen je "
    "laufendem Meter und Stunde; leistung-Parameter "
    "von F_STUNDEN für die Rissvorgänge (V_RISS_AUFFRAESEN, V_RISS_VERGUSS).",
    "riss_vergussmasse_kg_pro_m": "Ansatz Vergussmasse je laufendem Meter Riss; "
    "ansatz-Parameter von F_MENGE_ANSATZ (kg→t "
    "konvertiert), speist die Vergussmasse-Materialzeile.",
    "voranstrich_pauschal_eur_pro_m": "Pauschalsatz Voranstrich je laufendem Meter "
    "Riss; satz-Parameter der zweiten Riss-"
    "Materialzeile (F_KOSTEN_SATZ), summiert mit der Vergussmasse.",
    "schieberkappen_pro_h": "Anzahl regulierter Schieberkappen je Stunde; "
    "leistung-Parameter von F_STUNDEN für "
    "V_SCHIEBERKAPPEN_REG.",
    "moertel_kleinmaterial_eur_pro_st": "Mörtel-/Kleinmaterialkosten je Schieberkappe; "
    "satz-Parameter der F_KOSTEN_SATZ-"
    "Materialzeile.",
    "thermo_leistung_t_pro_h": "Durchsatz Thermocontainer-Schadstellensanierung je "
    "Stunde (tonnenbezogen); leistung-"
    "Parameter von F_STUNDEN für die Thermo-Vorgänge.",
    "emulsion_anteil_eur_pro_t": "Emulsionskostenanteil je Tonne Einbaumenge "
    "(Schichtenverbund Thermo); satz-Parameter der "
    "Thermo-Emulsions-Materialzeile.",
    "thermo_container_geraetekosten_eur_pro_h": "Gerätekosten Thermocontainer je "
    "Stunde (Pauschalsatz, kein Verbrauch); stundensatz-"
    "Parameter der Thermo-Maschinenzeile (F_MASCHINE).",
    "fraesgut_anteil_t_pro_t_einbau": "Anteil anfallendes Fräsgut je Tonne Einbaumenge "
    "(Thermo-Ausschneiden); ansatz-Parameter "
    "von F_MENGE_ANSATZ für die Fräsgut-Menge (Entsorgung + Abtransport).",
    "entsorgung_betonaufbruch_eur_pro_t": "Entsorgungssatz Betonaufbruch "
    "(Tiefbordstein) je Tonne; satz-Parameter der Tiefbord-"
    "Entsorgungszeile. PLATZHALTER.",
    "anteil_anspritzen": "Zeitanteil der Teiltätigkeit Anspritzen an den "
    "Thermo-Vorgangsstunden (0–1); anteil-"
    "Parameter von F_MASCHINE und F_LOHN.",
    "anteil_ausschneiden_fraesen": "Zeitanteil der Teiltätigkeit Ausschneiden/Fräsen "
    "an den Thermo-Vorgangsstunden (0–1); "
    "anteil-Parameter von F_MASCHINE und F_LOHN.",
    "anteil_saeubern": "Zeitanteil der Teiltätigkeit Säubern an den "
    "Thermo-Vorgangsstunden (0–1); anteil-"
    "Parameter von F_LOHN.",
    "strip_length_m": "Länge des Streckenabschnitts in m (Projektkontext-Global); "
    "Quelle der gebuchten laenge_m, "
    "wenn keine Positionsmenge vorliegt.",
    "strip_width_m": "Breite des Streckenabschnitts in m (Projektkontext-Global); geht "
    "mit der Länge in die "
    "Streifengeometrie (Fläche/Volumen) ein.",
    "strip_depth_cm": "Tiefe/Dicke des Streckenabschnitts in cm "
    "(Projektkontext-Global); Tiefen-Kante der "
    "Streifen-Volumenrechnung.",
}

# The agent Vorgänge's kostenvariablen at Stand 11 — order-sensitive (Nachweis cost-line
# order); the Rechnungen below reproduce exactly these cost lines in exactly this order.
AGENT_KOSTENVARIABLEN: dict[str, list[tuple[str, str]]] = {
    "V_RISS_AUFFRAESEN": [
        ("Maschine", "mk_riss_auffraesen"),
        ("Lohn", "lohn_riss_auffraesen"),
    ],
    "V_RISS_VERGUSS": [
        ("Material", "mk_riss_verguss_material"),
        ("Maschine", "mk_riss_verguss_geraet"),
        ("Lohn", "lohn_riss_verguss"),
    ],
    "V_SCHIEBERKAPPEN_REG": [
        ("Material", "mat_schieberkappe_reg"),
        ("Lohn", "lohn_schieberkappe_reg"),
    ],
    "V_THERMO_ANSPRITZEN": [
        ("Material", "mat_thermo_emulsion"),
        ("Maschine", "mk_thermo_anspritzen"),
        ("Lohn", "lohn_thermo_anspritzen"),
    ],
    "V_THERMO_AUSSCHNEIDEN_ODER_FRAESEN": [
        ("Maschine", "mk_thermo_ausschneiden"),
        ("Lohn", "lohn_thermo_ausschneiden"),
        ("Abtransport", "trans_thermo_fraesgut"),
        ("Entsorgung", "ent_thermo_fraesgut"),
    ],
    "V_THERMO_SAEUBERN": [("Lohn", "lohn_thermo_saeubern")],
    "V_THERMO_VERFUELLEN_VERDICHTEN": [
        ("Material", "mat_thermo_asphalt"),
        ("Lohn", "lohn_thermo_einbau"),
        ("Maschine", "mk_thermo_container"),
    ],
    "V_TIEFBORD_AUFN": [
        ("Maschine", "mk_tiefbord_aufn"),
        ("Lohn", "lohn_tiefbord_aufn"),
        ("Entsorgung", "ent_tiefbord_aufbruch"),
        ("Abtransport", "trans_tiefbord_aufbruch"),
    ],
}


# --------------------------------------------------------------------------- #
# Rechnungen of the 8 agent Vorgänge (Appendix B — same helpers as vorgaenge.py)
# --------------------------------------------------------------------------- #
def _i(
    formel,
    variable=None,
    ergebnis_einheit=None,
    bezeichnung=None,
    einheiten=None,
    **bindung,
) -> FormelInstanz:
    return FormelInstanz(
        formel=formel,
        bindung=bindung,
        einheiten=einheiten or {},
        ergebnis_einheit=ergebnis_einheit,
        variable=variable,
        bezeichnung=bezeichnung,
    )


def _leistung(basisleistung) -> FormelInstanz:
    return _i("F_LEISTUNG_ERSCHWERT", basisleistung=basisleistung)


def _arbeitszeit(menge) -> FormelInstanz:
    return _i("F_STUNDEN", menge=menge, leistung="formel.leistung")


def _maschine(bez, geraet, anteil=None) -> FormelInstanz:
    b = {
        "stunden": "formel.arbeitszeit",
        "stundensatz": f"stammdaten.{geraet}_stundensatz_eur",
        "verbrauch": f"stammdaten.{geraet}_l_pro_h",
        "kraftstoffpreis": "stammdaten.kraftstoffpreis_eur_pro_l",
    }
    if anteil is not None:
        b["anteil"] = anteil
    return _i("F_MASCHINE", bezeichnung=bez, **b)


def _geraet_pauschal(bez, satz) -> FormelInstanz:
    return _i(
        "F_MASCHINE", bezeichnung=bez, stunden="formel.arbeitszeit", stundensatz=satz
    )


def _lohn(bez, kolonne=None, anteil=None) -> FormelInstanz:
    b = {"stunden": "formel.arbeitszeit", "stundenlohn": "stammdaten.stundenlohn_eur"}
    if kolonne is not None:
        b["kolonne"] = kolonne
    if anteil is not None:
        b["anteil"] = anteil
    return _i("F_LOHN", bezeichnung=bez, **b)


def _kosten(bez, menge, satz) -> FormelInstanz:
    return _i("F_KOSTEN_SATZ", bezeichnung=bez, menge=menge, satz=satz)


def _transport(bez, menge, entfernung) -> FormelInstanz:
    return _i(
        "F_TRANSPORT",
        bezeichnung=bez,
        menge=menge,
        satz="stammdaten.transport_eur_pro_t_km",
        entfernung=entfernung,
    )


def _staffel_fraesgut() -> FormelInstanz:
    return _i(
        "F_STAFFEL",
        wert="kontext.fraesgut_klasse",
        stufe1="1",
        satz1="stammdaten.ent_fraesgut_verwertbar",
        stufe2="2",
        satz2="stammdaten.ent_fraesgut_belastet",
        satz3="stammdaten.ent_fraesgut_pechhaltig",
    )


def _thermo_basis() -> dict[str, FormelInstanz]:
    """Shared THERMO core: Asphalt-Tonnage (materialisiert menge_t, so t-billing books
    it), Thermocontainer-Leistung, Arbeitszeit. Each Vorgang scales via anteil per
    Teiltätigkeit."""
    return {
        "volumen": _i(
            "F_VOLUMEN_FLAECHE",
            flaeche="kontext.flaeche_m2",
            dicke="kontext.einbaudicke_cm",
        ),
        "menge": _i(
            "F_MENGE_VOLUMEN",
            variable="menge_t",
            volumen="formel.volumen",
            dichte="stammdaten.dichte_asphalt_t_pro_m3",
        ),
        "leistung": _leistung("stammdaten.thermo_leistung_t_pro_h"),
        "arbeitszeit": _arbeitszeit("formel.menge"),
    }


def agent_rechnungen() -> dict[str, VorgangRechnung]:
    """The 8 agent Vorgänge as base-formula instantiations, cost lines in
    kostenvariablen order."""
    return {
        "V_RISS_AUFFRAESEN": VorgangRechnung(
            instanzen={
                "leistung": _leistung("stammdaten.riss_sanierung_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MASCHINE: [
                    _maschine("Fugenschneider (Riss auffräsen)", "schneider")
                ],
                KA.LOHN: [_lohn("Sanierungskolonne", "kontext.anzahl_arbeiter")],
            },
        ),
        "V_RISS_VERGUSS": VorgangRechnung(
            instanzen={
                "leistung": _leistung("stammdaten.riss_sanierung_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
                "vergussmasse": _i(
                    "F_MENGE_ANSATZ",
                    einheiten={"ansatz": "t/m"},
                    ansatz="stammdaten.riss_vergussmasse_kg_pro_m",
                    bezugsmenge="kontext.laenge_m",
                ),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Vergussmasse",
                        "formel.vergussmasse",
                        "stammdaten.fugenmasse_preis_eur_pro_t",
                    ),
                    _kosten(
                        "Voranstrich",
                        "kontext.laenge_m",
                        "stammdaten.voranstrich_pauschal_eur_pro_m",
                    ),
                ],
                KA.MASCHINE: [_maschine("Fugengerät (Verguss)", "fugen_geraet")],
                KA.LOHN: [_lohn("Sanierungskolonne", "kontext.anzahl_arbeiter")],
            },
        ),
        "V_SCHIEBERKAPPEN_REG": VorgangRechnung(
            instanzen={
                "leistung": _leistung("stammdaten.schieberkappen_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.anzahl_st"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Mörtel/Kleinmaterial je Kappe",
                        "kontext.anzahl_st",
                        "stammdaten.moertel_kleinmaterial_eur_pro_st",
                    )
                ],
                KA.LOHN: [_lohn("Regulierkolonne", "kontext.anzahl_arbeiter")],
            },
        ),
        "V_THERMO_ANSPRITZEN": VorgangRechnung(
            instanzen=_thermo_basis(),
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Bitumenemulsion (Ansatz je t Einbaumenge)",
                        "formel.menge",
                        "stammdaten.emulsion_anteil_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [
                    _maschine(
                        "Rampenspritzgerät (Zeitanteil)",
                        "spritzgeraet",
                        anteil="stammdaten.anteil_anspritzen",
                    )
                ],
                KA.LOHN: [
                    _lohn(
                        "Thermokolonne (Anspritzen)",
                        "kontext.anzahl_arbeiter",
                        anteil="stammdaten.anteil_anspritzen",
                    )
                ],
            },
        ),
        "V_THERMO_AUSSCHNEIDEN_ODER_FRAESEN": VorgangRechnung(
            instanzen={
                **_thermo_basis(),
                "fraesgutmenge": _i(
                    "F_MENGE_ANSATZ",
                    ansatz="stammdaten.fraesgut_anteil_t_pro_t_einbau",
                    bezugsmenge="formel.menge",
                ),
                "entsorgungssatz": _staffel_fraesgut(),
            },
            kosten={
                KA.MASCHINE: [
                    _maschine(
                        "Fugenschneider (Zeitanteil)",
                        "schneider",
                        anteil="stammdaten.anteil_ausschneiden_fraesen",
                    )
                ],
                KA.LOHN: [
                    _lohn(
                        "Thermokolonne (Ausschneiden/Fräsen)",
                        "kontext.anzahl_arbeiter",
                        anteil="stammdaten.anteil_ausschneiden_fraesen",
                    )
                ],
                KA.ABTRANSPORT: [
                    _transport(
                        "Fräsgut zur Deponie",
                        "formel.fraesgutmenge",
                        "kontext.entfernung_deponie_km",
                    )
                ],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Fräsgut entsorgen/verwerten",
                        "formel.fraesgutmenge",
                        "formel.entsorgungssatz",
                    )
                ],
            },
        ),
        "V_THERMO_SAEUBERN": VorgangRechnung(
            instanzen=_thermo_basis(),
            kosten={
                KA.LOHN: [
                    _lohn(
                        "Thermokolonne (Säubern)",
                        "kontext.anzahl_arbeiter",
                        anteil="stammdaten.anteil_saeubern",
                    )
                ],
            },
        ),
        "V_THERMO_VERFUELLEN_VERDICHTEN": VorgangRechnung(
            instanzen=_thermo_basis(),
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Asphaltmischgut",
                        "formel.menge",
                        "stammdaten.asphalt_preis_eur_pro_t",
                    )
                ],
                KA.LOHN: [
                    _lohn(
                        "Thermokolonne (Verfüllen/Verdichten)",
                        "kontext.anzahl_arbeiter",
                    )
                ],
                KA.MASCHINE: [
                    _geraet_pauschal(
                        "Thermocontainer (Gerätekosten)",
                        "stammdaten.thermo_container_geraetekosten_eur_pro_h",
                    )
                ],
            },
        ),
        "V_TIEFBORD_AUFN": VorgangRechnung(
            instanzen={
                # 25 m/h war eine Konstanten-Formel; promoted to a visible literal
                # binding.
                "leistung": _leistung("25"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
                # 0.06 t/m Bordstein-Aufbruchmasse: promoted magic number (Appendix B).
                "tonnage": _i(
                    "F_MENGE_ANSATZ", ansatz="0.06", bezugsmenge="kontext.laenge_m"
                ),
            },
            kosten={
                KA.MASCHINE: [
                    _geraet_pauschal(
                        "Bagger (Pauschalsatz)", "stammdaten.bagger_stundensatz_eur"
                    )
                ],
                KA.LOHN: [_lohn("Aufnahmekolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Betonaufbruch entsorgen",
                        "formel.tonnage",
                        "stammdaten.entsorgung_betonaufbruch_eur_pro_t",
                    )
                ],
                KA.ABTRANSPORT: [
                    _transport(
                        "Aufbruch zur Deponie",
                        "formel.tonnage",
                        "kontext.entfernung_deponie_km",
                    )
                ],
            },
        ),
    }


# --------------------------------------------------------------------------- #
# Migration steps
# --------------------------------------------------------------------------- #
class MigrationsAbbruch(Exception):
    """Pre-state drift or validation failure — the transaction rolls back."""


class _DryRun(Exception):
    """Raised after the report on --dry-run so the UoW rolls everything back."""


def _json(wert: Any) -> Any:
    return json.loads(wert) if isinstance(wert, str) else wert


async def _verifiziere_vorzustand(conn: AsyncConnection) -> dict[str, list[str]]:
    """Assert the active catalog is exactly the state this script's mapping was derived
    from."""
    fehler: list[str] = []

    formeln = (
        (
            await conn.execute(
                text(
                    "SELECT name, ausdruck, version, benutzer FROM katalog_formeln "
                    "WHERE status='aktiv'"
                )
            )
        )
        .mappings()
        .all()
    )
    seed_formeln = [f["name"] for f in formeln if f["benutzer"] == "seed"]
    for f in formeln:
        if f["benutzer"] == "seed":
            if f["version"] != 1:
                fehler.append(
                    f"Seed-Formel '{f['name']}' wurde überschrieben (v{f['version']}) "
                    f"— "
                    "die Fixture-Transformation deckt sie nicht mehr."
                )
        elif f["name"] not in AGENT_FORMELN:
            fehler.append(
                f"Unbekannte aktive Formel '{f['name']}' — Transformation fehlt."
            )
        elif f["ausdruck"] != AGENT_FORMELN[f["name"]]:
            fehler.append(
                f"Formel '{f['name']}' weicht vom Spec-Ausdruck ab: {f['ausdruck']!r}"
            )
    for name in set(AGENT_FORMELN) - {f["name"] for f in formeln}:
        fehler.append(f"Erwartete Agent-Formel '{name}' ist nicht aktiv.")

    vorgaenge = (
        (
            await conn.execute(
                text(
                    "SELECT code, version, benutzer, kostenvariablen FROM "
                    "katalog_vorgaenge WHERE status='aktiv'"
                )
            )
        )
        .mappings()
        .all()
    )
    fixture_codes = {v.code for v in VORGAENGE.values()}
    for v in vorgaenge:
        if v["code"] in fixture_codes:
            if v["version"] != 1 or v["benutzer"] != "seed":
                fehler.append(
                    f"Fixture-Vorgang '{v['code']}' wurde verändert (v{v['version']}, "
                    f"{v['benutzer']}) — die Fixture-Rechnung deckt ihn nicht mehr."
                )
        elif v["code"] not in AGENT_KOSTENVARIABLEN:
            fehler.append(
                f"Unbekannter aktiver Vorgang '{v['code']}' — Rechnung fehlt."
            )
        elif (
            list(_json(v["kostenvariablen"]).items())
            != AGENT_KOSTENVARIABLEN[v["code"]]
        ):
            fehler.append(
                f"Vorgang '{v['code']}': kostenvariablen weichen vom Spec ab: "
                f"{_json(v['kostenvariablen'])!r}"
            )
    aktive_codes = {v["code"] for v in vorgaenge}
    for code in (fixture_codes | set(AGENT_KOSTENVARIABLEN)) - aktive_codes:
        fehler.append(f"Erwarteter Vorgang '{code}' ist nicht aktiv.")

    if fehler:
        raise MigrationsAbbruch("Vorzustand weicht ab:\n  " + "\n  ".join(fehler))
    return {
        "seed_formeln": sorted(seed_formeln),
        "agent_formeln": sorted(set(AGENT_FORMELN)),
    }


async def _scrubbe_formel_name(conn: AsyncConnection) -> int:
    """Drop the retired `formel_name` key from every stored Auflösungsschritt (all rows,
    history included) — the tightened AufloesungsSchritt (extra=forbid) no longer parses
    it. No information is lost: the key was always null except on FORMEL steps, where it
    equaled the variable name by construction."""
    rows = (
        await conn.execute(
            select(katalog_variablen.c.zeile_uuid, katalog_variablen.c.aufloesung)
        )
    ).all()
    n = 0
    for zeile_uuid, aufloesung in rows:
        schritte = _json(aufloesung)
        if any("formel_name" in s for s in schritte):
            gesaeubert = [
                {k: v for k, v in s.items() if k != "formel_name"} for s in schritte
            ]
            await conn.execute(
                update(katalog_variablen)
                .where(katalog_variablen.c.zeile_uuid == zeile_uuid)
                .values(aufloesung=gesaeubert)
            )
            n += 1
    return n


async def _archiviere(conn: AsyncConnection, tabelle: Table, *bedingungen: Any) -> int:
    now = (await conn.execute(select(func.clock_timestamp()))).scalar_one()
    ergebnis = await conn.execute(
        update(tabelle)
        .where(tabelle.c.status == KatalogStatus.AKTIV.value, *bedingungen)
        .values(status=KatalogStatus.ARCHIVIERT.value, gueltig_bis=now)
    )
    return ergebnis.rowcount


def _cutover_bundle() -> KatalogBundle:
    vorgaenge: list[BundleVorgang] = [
        BundleVorgang(
            code=v.code,
            name=v.name,
            ausfuehrungsart_code=v.ausfuehrungsart.code if v.ausfuehrungsart else None,
            betriebsart_code=v.betriebsart_code,
            leistung_instanz=v.leistung_instanz,
            kosten_bindung=v.kosten_bindung,
            rechnung=v.rechnung,
        )
        for v in VORGAENGE.values()
    ]
    # All surviving fixture variables (Phase 3): supersede the stale live rows with the
    # prose-rich fixture definitions. Values are unchanged (parity-neutral); only
    # beschreibung + cascade prompts are added. flaeche_m2/menge_t are the kontext
    # geometry placeholders reintroduced in Phase 1 — they ride along here as ordinary
    # members of KONTEXT_VARIABLEN.
    variablen = [
        BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=d)
        for d in STAMMDATEN_VARIABLEN.values()
    ] + [
        BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=d)
        for d in KONTEXT_VARIABLEN.values()
    ]
    return KatalogBundle(
        formeln=list(FORMELN.values()), vorgaenge=vorgaenge, variablen=variablen
    )


async def _db_only_prosa_variablen(conn: AsyncConnection) -> list[BundleVariable]:
    """Read each DB-only agent/strip variable's active definition and re-emit it with
    its authored beschreibung (Phase-3 prose). Value + cascade are taken verbatim from
    the active row, so the supersede is parity-neutral. A name in the prose table that
    is not active is an error — the corpus this script targets has changed."""
    namen = list(DB_ONLY_VARIABLEN_PROSA)
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT name, gruppe, bezeichnung, einheit, datentyp, llm_kontext, "
                    "aufloesung "
                    "FROM katalog_variablen WHERE status='aktiv' AND name = ANY(:namen)"
                ).bindparams(namen=namen)
            )
        )
        .mappings()
        .all()
    )
    gefunden = {r["name"] for r in rows}
    fehlend = set(namen) - gefunden
    if fehlend:
        raise MigrationsAbbruch(
            f"DB-only Variablen nicht aktiv (Prosa-Backfill): {sorted(fehlend)}"
        )
    variablen: list[BundleVariable] = []
    for r in rows:
        definition = VariableDefinition.model_validate(
            {
                "name": r["name"],
                "bezeichnung": r["bezeichnung"],
                "beschreibung": DB_ONLY_VARIABLEN_PROSA[r["name"]],
                "einheit": r["einheit"],
                "datentyp": r["datentyp"],
                "llm_kontext": r["llm_kontext"],
                "aufloesung": _json(r["aufloesung"]),
            }
        )
        variablen.append(
            BundleVariable(gruppe=VariablenGruppe(r["gruppe"]), definition=definition)
        )
    return variablen


async def _agent_bundle_vorgaenge(conn: AsyncConnection) -> list[BundleVorgang]:
    """The 8 agent Vorgänge: identity/machine seam from the active row, Rechnung from
    the spec."""
    rechnungen = agent_rechnungen()
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT code, name, ausfuehrungsart_code, betriebsart_code, "
                    "kosten_bindung "
                    "FROM katalog_vorgaenge WHERE status='aktiv' AND code = ANY(:codes)"
                ).bindparams(codes=list(rechnungen))
            )
        )
        .mappings()
        .all()
    )
    return [
        BundleVorgang(
            code=r["code"],
            name=r["name"],
            ausfuehrungsart_code=r["ausfuehrungsart_code"],
            betriebsart_code=r["betriebsart_code"],
            leistung_instanz="leistung",
            kosten_bindung=_json(r["kosten_bindung"]),
            rechnung=rechnungen[r["code"]],
        )
        for r in rows
    ]


async def _schreibe_bundle(
    repo: KatalogRepository, bundle: KatalogBundle
) -> dict[str, int]:
    bundle_uuid = uuid4()
    zaehler: dict[str, int] = {}

    async def aktiv(entitaet: KatalogEntitaet, schluessel: str, record: dict) -> None:
        payload = {c: record[c] for c in KATALOG_REGISTRY[entitaet].payload}
        z = await repo.neue_version(
            entitaet, schluessel, payload, BENUTZER, bundle_uuid
        )
        await repo.aktiviere(entitaet, z.zeile_uuid)
        zaehler[entitaet.value] = zaehler.get(entitaet.value, 0) + 1

    for f in bundle.formeln:
        await aktiv(KatalogEntitaet.FORMELN, f.name, f.model_dump(mode="json"))
    for bv in bundle.variablen:
        record = bv.definition.model_dump(mode="json") | {"gruppe": bv.gruppe.value}
        await aktiv(KatalogEntitaet.VARIABLEN, bv.definition.name, record)
    for v in bundle.vorgaenge:
        await aktiv(KatalogEntitaet.VORGAENGE, v.code, v.model_dump(mode="json"))
    return zaehler


def _bericht(
    vorzustand: dict[str, list[str]],
    formel_variablen: list[str],
    zaehler: dict[str, int],
    survivors: dict[str, list[str]],
) -> str:
    z = [
        "# Variablen-Disposition — Rezept-Cutover (Phasen 2 + 3)",
        "",
        "Emittiert von `scripts.migrate_rezept_katalog` (REZEPT_REDESIGN_PLAN Appendix "
        "C + §2.6).",
        "",
        "## Formeln",
        f"- Stillgelegt: "
        f"{len(vorzustand['seed_formeln']) + len(vorzustand['agent_formeln'])} "
        f"({len(vorzustand['seed_formeln'])} Seed + {len(vorzustand['agent_formeln'])} "
        f"Agent) "
        f"→ ersetzt durch {zaehler.get('formeln', 0)} Basisformeln + "
        f"Vorgang-Rechnungen.",
        "- Merges: tonnage_fraesgut ≡ tonnage_aufbruch; mat_thermo_asphalt ≡ "
        "materialkosten_asphalt;",
        "  lohn_riss_auffraesen ≡ lohn_riss_verguss (je eine F_LOHN-Instanz pro "
        "Vorgang).",
        "- Promotes: tiefbord_leistung_m_pro_h (25 m/h) und 0.06 t/m Bordstein-Masse "
        "sind jetzt",
        "  sichtbare Literal-Bindungen auf V_TIEFBORD_AUFN.",
        "- Ersatzlos: calc_volumen_m3 (verwaist — kein Konsument in Katalog oder "
        "Code).",
        "",
        "## Variablen",
        f"- Stillgelegt (gruppe=formel, Ergebnis-Zwischenwerte): "
        f"{len(formel_variablen)}",
        "  " + ", ".join(formel_variablen),
        "- Stillgelegt (stammdaten): entsorgung_fraesasphalt_eur_pro_t — die "
        "geschattete",
        "  Back-Compat-Konstante; der Satz kommt jetzt aus F_STAFFEL-Instanzen.",
        "- Neu (kontext): flaeche_m2, menge_t — Geometrie-Platzhalter; die Herleitung "
        "übernehmen",
        "  Vorgang-Instanzen mit `variable`-Seam.",
        "",
        "## Prosa-Backfill (Phase 3, §2.6)",
        f"- Alle überlebenden Fixture-Variablen ({len(STAMMDATEN_VARIABLEN)} "
        f"stammdaten + "
        f"{len(KONTEXT_VARIABLEN)} kontext) mit retrieval-tauglicher beschreibung "
        f"superseded "
        "(Werte unverändert — paritätsneutral).",
        f"- {len(DB_ONLY_VARIABLEN_PROSA)} DB-only Variablen (Agent-Rezepte "
        f"thermo/riss/tiefbord/"
        "schieberkappen + Streifen-Geometrie) mit hier autorisierter beschreibung "
        "versehen.",
        "- Mandatory-Prose-Validierung aktiv: neue/geänderte Formeln UND Variablen "
        "ohne beschreibung "
        "werden abgelehnt (validierung.py Rule 1/1b).",
    ]
    for gruppe, namen in sorted(survivors.items()):
        z.append(f"- Überlebt ({gruppe}): {len(namen)}")
        z.append("  " + ", ".join(namen))
    z += [
        "",
        "## Abweichung von Appendix C (bewusst)",
        "- Maschinen-Stundensätze/-Verbräuche bleiben Stammdaten-Variablen: sie sind "
        "die",
        "  No-Machine-Defaults der F_MASCHINE-Bindungen (kosten_bindung überschreibt "
        "sie aus dem",
        "  Eigenschafts-Beutel). Ontologie-Phase (3) entscheidet über weitere "
        "Verlagerung.",
        "- Kurvenparameter (Tiefenkonstante/Grenzen) stehen als Literale in den "
        "Instanz-Bindungen,",
        "  nicht auf Leistungsprofilen — die Engine liest Profile heute nur als "
        "Flachwert.",
        "",
    ]
    return "\n".join(z)


async def migriere(conn: AsyncConnection, repo: KatalogRepository) -> str:
    vorzustand = await _verifiziere_vorzustand(conn)

    n_scrub = await _scrubbe_formel_name(conn)
    print(
        f"aufloesung-Scrub (formel_name-Altlast): {n_scrub} Variablen-Zeilen bereinigt"
    )

    # Retire the old corpus first, so bundle validation sees the post-retirement stand
    # (otherwise the new kontext flaeche_m2/menge_t would collide with the FORMEL-gruppe
    # rows).
    n_formeln = await _archiviere(conn, katalog_formeln)
    formel_variablen = sorted(
        (
            await conn.execute(
                select(katalog_variablen.c.name).where(
                    katalog_variablen.c.status == KatalogStatus.AKTIV.value,
                    katalog_variablen.c.gruppe == VariablenGruppe.FORMEL.value,
                )
            )
        )
        .scalars()
        .all()
    )
    n_formel_vars = await _archiviere(
        conn,
        katalog_variablen,
        katalog_variablen.c.gruppe == VariablenGruppe.FORMEL.value,
    )
    n_schatten = await _archiviere(
        conn,
        katalog_variablen,
        katalog_variablen.c.gruppe == VariablenGruppe.STAMMDATEN.value,
        katalog_variablen.c.name == "entsorgung_fraesasphalt_eur_pro_t",
    )
    print(
        f"stillgelegt: {n_formeln} Formeln, {n_formel_vars} Formel-Variablen, "
        f"{n_schatten} Schatten-Konstante(n)"
    )

    bundle = _cutover_bundle()
    bundle.vorgaenge.extend(await _agent_bundle_vorgaenge(conn))
    if len(bundle.vorgaenge) != len(VORGAENGE) + len(AGENT_KOSTENVARIABLEN):
        raise MigrationsAbbruch("Agent-Vorgänge unvollständig geladen.")
    # Phase 3: fold the prose-rich variables into the cutover — all fixture survivors
    # ride in the bundle above; the DB-only agent/strip variables get their authored
    # beschreibung here.
    bundle.variablen.extend(await _db_only_prosa_variablen(conn))

    stand = await lade_stand(repo)
    bericht = pruefe_bundle(bundle, stand)
    if bericht.fehler:
        raise MigrationsAbbruch(
            "Cutover-Bundle ungültig:\n  " + "\n  ".join(bericht.fehler)
        )

    zaehler = await _schreibe_bundle(repo, bundle)
    stand_zeile = await repo.stand_beruehren(benutzer=BENUTZER, aktivierung=True)
    print(f"aktiviert: {zaehler} — Katalog-Stand {stand_zeile.version}")

    # Shape gate: the migrated catalog must load through the provider before commit.
    geladen = await lade_katalog(conn)
    if geladen is None:
        raise MigrationsAbbruch("Provider-Smoke-Load fand keinen Katalog.")
    print(f"Provider-Smoke-Load ok: {geladen}")

    survivors: dict[str, list[str]] = {}
    for gruppe in (VariablenGruppe.STAMMDATEN, VariablenGruppe.KONTEXT):
        survivors[gruppe.value] = sorted(
            (
                await conn.execute(
                    select(katalog_variablen.c.name).where(
                        katalog_variablen.c.status == KatalogStatus.AKTIV.value,
                        katalog_variablen.c.gruppe == gruppe.value,
                    )
                )
            )
            .scalars()
            .all()
        )
    return _bericht(vorzustand, formel_variablen, zaehler, survivors)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cutover auf das Basisformel-System (Phase 2)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="alles ausführen und berichten, dann zurückrollen",
    )
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    try:
        try:
            async with unit_of_work(engine) as uow:
                bericht = await migriere(uow.conn, uow.katalog)
                if args.dry_run:
                    raise _DryRun
        except _DryRun:
            print("\n" + bericht)
            print("--dry-run: Transaktion zurückgerollt, Katalog unverändert.")
        else:
            BERICHT_PFAD.parent.mkdir(parents=True, exist_ok=True)
            BERICHT_PFAD.write_text(bericht)
            print(f"\nDispositions-Bericht: {BERICHT_PFAD}")
            print(
                "Nächster Schritt (harte Parität): uv run python -m "
                "scripts.ekt_snapshot --vergleich"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
