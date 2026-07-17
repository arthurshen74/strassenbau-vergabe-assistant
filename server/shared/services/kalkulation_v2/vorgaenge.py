"""
vorgaenge.py — reusable Vorgänge (discrete work operations) and their Rechnungen.

Each Vorgang carries a VorgangRechnung: named Formel-Instanzen (Leistung, Arbeitszeit,
Mengengerüst, Kurven) plus die Kostenzeilen je Kostenart. Every entry INSTANTIATES a
base formula from formel.py — a dict binding of the formula's declared parameters onto
kontext/stammdaten variables, sibling instanzen ("formel.<name>") or literals; unit
scaling happens at the binding seam (einheiten.py), never in an expression.

Conventions: the productivity instanz is always named "leistung" (a bound machine's
Leistungsprofil overrides it via leistung_instanz), the duration instanz "arbeitszeit".
Instanzen that materialize a bookable variable (menge_t, flaeche_m2) declare it via
`variable`, so a booked LV-Menge wins over deriving. Exports VORGAENGE.
"""

from shared.services.kalkulation_v2.model import (
    FormelInstanz,
    Kostenart as KA,
    Vorgang,
    VorgangRechnung as R,
)
from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN as AA


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


def _leistung(basisleistung, erschwernisfaktor=None) -> FormelInstanz:
    b = {"basisleistung": basisleistung}
    if erschwernisfaktor:
        b["erschwernisfaktor"] = erschwernisfaktor
    return _i("F_LEISTUNG_ERSCHWERT", **b)


def _arbeitszeit(menge) -> FormelInstanz:
    return _i("F_STUNDEN", menge=menge, leistung="formel.leistung")


def _maschine(bez, geraet, verbrauch=None) -> FormelInstanz:
    """One machine cost line; `geraet` is the Stammdaten rate prefix
    (<geraet>_stundensatz_eur / <geraet>_l_pro_h), `verbrauch` overrides the fuel
    variable when it breaks the prefix."""
    return _i(
        "F_MASCHINE",
        bezeichnung=bez,
        stunden="formel.arbeitszeit",
        stundensatz=f"stammdaten.{geraet}_stundensatz_eur",
        verbrauch=verbrauch or f"stammdaten.{geraet}_l_pro_h",
        kraftstoffpreis="stammdaten.kraftstoffpreis_eur_pro_l",
    )


def _geraet_pauschal(bez, satz) -> FormelInstanz:
    """A lumped device rate without a fuel component (verbrauch stays 0)."""
    return _i(
        "F_MASCHINE", bezeichnung=bez, stunden="formel.arbeitszeit", stundensatz=satz
    )


def _lohn(bez, kolonne=None) -> FormelInstanz:
    b = {"stunden": "formel.arbeitszeit", "stundenlohn": "stammdaten.stundenlohn_eur"}
    if kolonne is not None:
        b["kolonne"] = kolonne
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


def _tonnage_schuettgut() -> FormelInstanz:
    """Liefermenge Schüttgut: gebuchtes Volumen × Baustoff-Rohdichte ×
    Verdichtungsfaktor."""
    return _i(
        "F_MENGE_VOLUMEN",
        volumen="kontext.volumen_m3",
        dichte="stammdaten.dichte_t_pro_m3",
        verdichtungsfaktor="stammdaten.verdichtungsfaktor",
    )


def _asphalt_menge(dicke) -> dict[str, FormelInstanz]:
    """Asphalt-Tonnage aus Fläche × Einbaudicke × Rohdichte; materialisiert menge_t, so
    a t-billed position's booked Menge wins over deriving."""
    return {
        "volumen": _i("F_VOLUMEN_FLAECHE", flaeche="kontext.flaeche_m2", dicke=dicke),
        "menge": _i(
            "F_MENGE_VOLUMEN",
            variable="menge_t",
            volumen="formel.volumen",
            dichte="stammdaten.dichte_asphalt_t_pro_m3",
        ),
    }


def _fraesgut() -> dict[str, FormelInstanz]:
    """Fräsgut-/Aufbruch-Tonnage (Fläche × Tiefe × Asphaltdichte) +
    Entsorgungssatz-Staffel."""
    return {
        "volumen": _i(
            "F_VOLUMEN_FLAECHE", flaeche="kontext.flaeche_m2", dicke="kontext.tiefe_cm"
        ),
        "tonnage": _i(
            "F_MENGE_VOLUMEN",
            volumen="formel.volumen",
            dichte="stammdaten.dichte_asphalt_t_pro_m3",
        ),
        "entsorgungssatz": _i(
            "F_STAFFEL",
            wert="kontext.fraesgut_klasse",
            stufe1="1",
            satz1="stammdaten.ent_fraesgut_verwertbar",
            stufe2="2",
            satz2="stammdaten.ent_fraesgut_belastet",
            satz3="stammdaten.ent_fraesgut_pechhaltig",
        ),
    }


def _mehrlagig(uebergaenge=None) -> dict[str, FormelInstanz]:
    """Fläche aus dem gebuchten Volumen, Lagenzahl, Arbeitsmenge (Fläche × Lagen [×
    Übergänge])."""
    inst = {
        "flaeche": _i(
            "F_FLAECHE_VOLUMEN",
            variable="flaeche_m2",
            volumen="kontext.volumen_m3",
            dicke="kontext.schichtdicke_m",
        ),
        "lagen": _i(
            "F_LAGEN",
            dicke="kontext.schichtdicke_m",
            max_lagendicke="stammdaten.max_lagendicke_b2_m",
        ),
    }
    b = {"basismenge": "formel.flaeche", "lagen": "formel.lagen"}
    if uebergaenge:
        b["uebergaenge"] = uebergaenge
    inst["arbeitsmenge"] = _i("F_ARBEITSMENGE", **b)
    return inst


def _ev2_uebergaenge() -> FormelInstanz:
    return _i(
        "F_UEBERGAENGE",
        x="kontext.ev2_ziel",
        x0="stammdaten.ev2_anker_min",
        y0="stammdaten.verdicht_uebergaenge_ev45",
        x1="stammdaten.ev2_anker_max",
        y1="stammdaten.verdicht_uebergaenge_ev100",
    )


VORGAENGE: dict[str, Vorgang] = {
    "BODENABTRAG": Vorgang(
        code="V_BODENABTRAG",
        name="Boden/Bankett abtragen und schälen",
        ausfuehrungsart=AA["BAGGER"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.bagger_leistung_m3_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.volumen_m3"),
                # Abtrag: gewachsene Dichte ohne Verdichtungszuschlag (Faktor ungebunden
                # = 1)
                "tonnage": _i(
                    "F_MENGE_VOLUMEN",
                    volumen="kontext.volumen_m3",
                    dichte="stammdaten.dichte_t_pro_m3",
                ),
            },
            kosten={
                KA.MASCHINE: [_maschine("Bagger", "bagger")],
                KA.LOHN: [_lohn("Erdbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Boden entsorgen (Z2)",
                        "formel.tonnage",
                        "stammdaten.entsorgung_boden_z2_eur_pro_t",
                    )
                ],
                KA.ABTRANSPORT: [
                    _transport(
                        "Boden zur Deponie",
                        "formel.tonnage",
                        "kontext.entfernung_deponie_km",
                    )
                ],
            },
        ),
    ),
    "EINBAU": Vorgang(
        code="V_EINBAU",
        name="Baustoff liefern, einbauen und verdichten",
        ausfuehrungsart=AA["RADLADER"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.einbau_leistung_m3_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.volumen_m3"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Baustoff",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [
                    _maschine("Radlader", "radlader"),
                    _maschine("Walze", "walze"),
                ],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Baustoff antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "ERSCHWERNIS": Vorgang(
        code="V_ERSCHWERNIS",
        name="Erschwernis-Zulage (Einfassungen)",
        ausfuehrungsart=AA["KOLONNE"],
        rechnung=R(
            kosten={
                KA.LOHN: [
                    _kosten(
                        "Erschwernis-Zulage",
                        "kontext.laenge_m",
                        "stammdaten.erschwernis_zulage_eur_pro_m",
                    )
                ],
            }
        ),
    ),
    "MARKIERUNG": Vorgang(
        code="V_MARKIERUNG",
        name="Markierung entfernen (Demarkierung)",
        ausfuehrungsart=AA["MARKFRAESE"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("kontext.markierung_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Markierungsfräse", "markfraese")],
                KA.LOHN: [_lohn("Fräskolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Demarkierungsabfall verwerten",
                        "kontext.laenge_m",
                        "stammdaten.entsorgung_demark_eur_pro_m",
                    )
                ],
            },
        ),
    ),
    "SCHNEIDEN": Vorgang(
        code="V_SCHNEIDEN",
        name="Asphaltbefestigung trennen/schneiden",
        ausfuehrungsart=AA["SCHNEIDER"],
        rechnung=R(
            instanzen={
                "leistung": _i(
                    "F_LEISTUNG_TIEFE",
                    tiefenkonstante="2.2",
                    untergrenze="18",
                    tiefe="kontext.tiefe_cm",
                ),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Fugenschneider", "schneider")],
                KA.LOHN: [_lohn("Schneidkolonne", "kontext.anzahl_arbeiter")],
            },
        ),
    ),
    "FRAESEN": Vorgang(
        code="V_FRAESEN",
        name="Asphalt fräsen",
        ausfuehrungsart=AA["KALTFRAESE"],
        rechnung=R(
            instanzen={
                "leistung": _i(
                    "F_LEISTUNG_TIEFE",
                    tiefenkonstante="10",
                    untergrenze="120",
                    tiefe="kontext.tiefe_cm",
                    erschwernisfaktor="kontext.erschwernisfaktor",
                ),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
                **_fraesgut(),
            },
            kosten={
                KA.MASCHINE: [_maschine("Kaltfräse", "kaltfraese")],
                KA.LOHN: [_lohn("Fräskolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Fräsgut entsorgen/verwerten",
                        "formel.tonnage",
                        "formel.entsorgungssatz",
                    )
                ],
                KA.ABTRANSPORT: [
                    _transport(
                        "Fräsgut zur Deponie",
                        "formel.tonnage",
                        "kontext.entfernung_deponie_km",
                    )
                ],
            },
        ),
    ),
    "AUFBRECHEN": Vorgang(
        code="V_AUFBRECHEN",
        name="Asphalt aufbrechen und aufnehmen",
        ausfuehrungsart=AA["BAGGER"],
        rechnung=R(
            instanzen={
                "leistung": _i(
                    "F_LEISTUNG_TIEFE",
                    tiefenkonstante="5",
                    untergrenze="30",
                    tiefe="kontext.tiefe_cm",
                ),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
                **_fraesgut(),
            },
            kosten={
                KA.MASCHINE: [_maschine("Bagger mit Meißel", "aufbruch")],
                KA.LOHN: [_lohn("Aufbruchkolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Aufbruch entsorgen/verwerten",
                        "formel.tonnage",
                        "formel.entsorgungssatz",
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
    ),
    "PLANUM": Vorgang(
        code="V_PLANUM",
        name="Planum herstellen",
        ausfuehrungsart=AA["GRADER"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.planum_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MASCHINE: [
                    _maschine("Grader", "grader"),
                    _maschine("Walze", "walze"),
                ],
                KA.LOHN: [_lohn("Planumkolonne", "kontext.anzahl_arbeiter")],
            },
        ),
    ),
    "VERDICHTEN": Vorgang(
        code="V_VERDICHTEN",
        name="Boden verdichten",
        ausfuehrungsart=AA["WALZE"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.walze_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Walze", "walze")],
                KA.LOHN: [_lohn("Walzenkolonne", "kontext.anzahl_arbeiter")],
            },
        ),
    ),
    "ASPHALT_EINBAU": Vorgang(
        code="V_ASPHALT_EINBAU",
        name="Asphaltschicht einbauen (Fertiger + Beschicker)",
        ausfuehrungsart=AA["ASPHALT_FERTIGER"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.asphalt_einbau_leistung_t_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.menge"),
                **_asphalt_menge("kontext.einbaudicke_cm"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Asphaltmischgut",
                        "formel.menge",
                        "stammdaten.asphalt_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [
                    _geraet_pauschal(
                        "Einbauzug (Fertiger+Beschicker+Walzen)",
                        "stammdaten.asphalt_zug_geraet_eur_pro_h",
                    )
                ],
                KA.LOHN: [_lohn("Einbaukolonne", "stammdaten.asphalt_kolonne")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Mischgut antransportieren",
                        "formel.menge",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "GRID_EINBAU": Vorgang(
        code="V_GRID_EINBAU",
        name="Asphalteinlage liefern und verlegen",
        ausfuehrungsart=AA["GRID_KOLONNE"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.grid_verlege_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Asphalteinlage",
                        "kontext.flaeche_m2",
                        "stammdaten.grid_preis_eur_pro_m2",
                    )
                ],
                KA.MASCHINE: [
                    _geraet_pauschal(
                        "Verlegegerät", "stammdaten.grid_geraet_stundensatz_eur"
                    )
                ],
                KA.LOHN: [
                    _lohn("Verlegekolonne (Fachpersonal)", "stammdaten.grid_kolonne")
                ],
            },
        ),
    ),
    "ABSTUMPFEN": Vorgang(
        code="V_ABSTUMPFEN",
        name="Abstumpfung aufbringen und einwalzen",
        ausfuehrungsart=AA["ABSTREUER"],
        rechnung=R(
            instanzen={
                "menge": _i(
                    "F_MENGE_ANSATZ",
                    einheiten={"ansatz": "t/m2"},
                    ansatz="kontext.abstreumenge_kg_pro_m2",
                    bezugsmenge="kontext.flaeche_m2",
                ),
                "leistung": _leistung("stammdaten.abstreuen_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Abstreukörnung",
                        "formel.menge",
                        "stammdaten.abstreukoernung_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Abstreuer", "abstreuer")],
                KA.LOHN: [_lohn("Abstreukolonne", "2")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Abstreugut aufnehmen/verwerten",
                        "kontext.flaeche_m2",
                        "stammdaten.ent_abstreu_eur_pro_m2",
                    )
                ],
            },
        ),
    ),
    "NAHT_AUFWEITEN": Vorgang(
        code="V_NAHT_AUFWEITEN",
        name="Naht/Anschluss zur Fuge aufweiten (schneiden)",
        ausfuehrungsart=AA["SCHNEIDER"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.naht_aufweiten_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Fugenschneider", "schneider")],
                KA.LOHN: [_lohn("Schneidkolonne", "2")],
            },
        ),
    ),
    "FUGENFUELLUNG": Vorgang(
        code="V_FUGENFUELLUNG",
        name="Fugenfüllung herstellen (Fugenmasse N2)",
        ausfuehrungsart=AA["FUGENGERAET"],
        rechnung=R(
            instanzen={
                "volumen": _i(
                    "F_VOLUMEN_QUADER",
                    breite="kontext.fugenspaltbreite_mm",
                    laenge="kontext.laenge_m",
                    tiefe="kontext.fugenspalttiefe_mm",
                ),
                "menge": _i(
                    "F_MENGE_VOLUMEN",
                    volumen="formel.volumen",
                    dichte="stammdaten.fugenmasse_dichte_t_pro_m3",
                ),
                "leistung": _leistung("stammdaten.fugenfuellung_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Fugenmasse N2 + Voranstrich",
                        "formel.menge",
                        "stammdaten.fugenmasse_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Fugengerät", "fugen_geraet")],
                KA.LOHN: [_lohn("Fugenkolonne", "2")],
            },
        ),
    ),
    "NAHT": Vorgang(
        code="V_NAHT",
        name="Naht in Asphaltschicht herstellen",
        ausfuehrungsart=AA["KOLONNE"],
        rechnung=R(
            instanzen={
                # Zweistufiger Ansatz: g/(m·cm) × Nahtdicke -> t/m, dann × Länge -> t
                "nahtsatz": _i(
                    "F_MENGE_ANSATZ",
                    ergebnis_einheit="t/m",
                    einheiten={"ansatz": "t/(m·cm)"},
                    ansatz="stammdaten.naht_material_g_pro_m_cm",
                    bezugsmenge="kontext.naht_dicke_cm",
                ),
                "menge": _i(
                    "F_MENGE_ANSATZ",
                    ansatz="formel.nahtsatz",
                    bezugsmenge="kontext.laenge_m",
                ),
                "leistung": _leistung("stammdaten.naht_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "PmB-Nahtmaterial",
                        "formel.menge",
                        "stammdaten.pmb_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Nahtgerät", "naht_geraet")],
                KA.LOHN: [_lohn("Nahtkolonne", "kontext.anzahl_arbeiter")],
            },
        ),
    ),
    # --- FSS decomposition (lay / profile / compact) ---
    "FSS_LEGEN": Vorgang(
        code="V_FSS_LEGEN",
        name="FSS liefern und legen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.radlader_leistung_m3_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.volumen_m3"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "FSS-Baustoff",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Radlader", "radlader")],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Baustoff antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "FSS_PROFIL": Vorgang(
        code="V_FSS_PROFIL",
        name="FSS profilieren (auf Höhe abziehen)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        rechnung=R(
            instanzen={
                **_mehrlagig(),
                "leistung": _leistung("stammdaten.profil_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Grader", "grader")],
                KA.LOHN: [_lohn("Graderfahrer")],
            },
        ),
    ),
    "FSS_VERDICHTEN": Vorgang(
        code="V_FSS_VERDICHTEN",
        name="FSS verdichten (Ev2-gerecht)",
        ausfuehrungsart=AA["WALZE"],
        rechnung=R(
            instanzen={
                **_mehrlagig("formel.uebergaenge"),
                "uebergaenge": _ev2_uebergaenge(),
                "leistung": _leistung("stammdaten.walze_uebergang_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Walze", "walze")],
                KA.LOHN: [_lohn("Walzenfahrer")],
            },
        ),
    ),
    "FSS_FERTIGER": Vorgang(
        code="V_FSS_FERTIGER",
        name="FSS liefern, legen und abziehen (Fertiger)",
        ausfuehrungsart=AA["FERTIGER"],
        rechnung=R(
            instanzen={
                "flaeche": _i(
                    "F_FLAECHE_VOLUMEN",
                    variable="flaeche_m2",
                    volumen="kontext.volumen_m3",
                    dicke="kontext.schichtdicke_m",
                ),
                "leistung": _leistung("stammdaten.fertiger_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.flaeche"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "FSS-Baustoff",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Fertiger", "fertiger")],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Baustoff antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    # --- Bankettbefestigung (lay / profile-to-Quergefälle / compact) ---
    "BANKETT_LEGEN": Vorgang(
        code="V_BANKETT_LEGEN",
        name="Bankettmaterial liefern und legen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.bankett_legen_leistung_m3_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.volumen_m3"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Bankettmaterial",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Radlader", "radlader")],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Material antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "BANKETT_PROFIL": Vorgang(
        code="V_BANKETT_PROFIL",
        name="Bankett profilgerecht abziehen (Quergefälle)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        rechnung=R(
            instanzen={
                **_mehrlagig(),
                "leistung": _leistung("stammdaten.bankett_profil_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Grader", "grader")],
                KA.LOHN: [_lohn("Graderfahrer")],
            },
        ),
    ),
    "BANKETT_VERDICHTEN": Vorgang(
        code="V_BANKETT_VERDICHTEN",
        name="Bankett verdichten (Ev2 ≥ 70)",
        ausfuehrungsart=AA["BANKETTWALZE"],
        rechnung=R(
            instanzen={
                **_mehrlagig("formel.uebergaenge"),
                "uebergaenge": _ev2_uebergaenge(),
                "leistung": _leistung(
                    "stammdaten.bankettwalze_uebergang_leistung_m2_pro_h"
                ),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Tandemwalze", "bankettwalze")],
                KA.LOHN: [_lohn("Walzenfahrer")],
            },
        ),
    ),
    "BANKETT_FERTIGER": Vorgang(
        code="V_BANKETT_FERTIGER",
        name="Bankett liefern, legen und profilieren (Fertiger)",
        ausfuehrungsart=AA["BANKETT_FERTIGER"],
        rechnung=R(
            instanzen={
                "flaeche": _i(
                    "F_FLAECHE_VOLUMEN",
                    variable="flaeche_m2",
                    volumen="kontext.volumen_m3",
                    dicke="kontext.schichtdicke_m",
                ),
                "leistung": _leistung("stammdaten.bankettfertiger_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.flaeche"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Bankettmaterial",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Bankettfertiger", "bankettfertiger")],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Material antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    # --- Grobkörniger Boden (Auffüllung unter Banketten, Einzelflächen) ---
    "BODEN_GROBK_LEGEN": Vorgang(
        code="V_BODEN_GROBK_LEGEN",
        name="Grobkörnigen Boden liefern und einbauen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.boden_legen_leistung_m3_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.volumen_m3"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Grobkörniger Boden",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Radlader", "radlader")],
                KA.LOHN: [_lohn("Einbaukolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Boden antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "BODEN_GROBK_PROFIL": Vorgang(
        code="V_BODEN_GROBK_PROFIL",
        name="Profilgerecht herstellen (Planum einbegriffen)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        rechnung=R(
            instanzen={
                **_mehrlagig(),
                "leistung": _leistung("stammdaten.boden_profil_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Grader", "grader")],
                KA.LOHN: [_lohn("Graderfahrer")],
            },
        ),
    ),
    "BODEN_GROBK_VERDICHTEN": Vorgang(
        code="V_BODEN_GROBK_VERDICHTEN",
        name="Boden verdichten (Standardverdichtung)",
        ausfuehrungsart=AA["WALZE"],
        rechnung=R(
            instanzen={
                # Fester Übergangs-Ansatz (kein Ev2 im LV), nicht die Ev2-Kurve
                **_mehrlagig("stammdaten.boden_verdicht_uebergaenge"),
                "leistung": _leistung(
                    "stammdaten.boden_verdicht_leistung_m2_pro_h_uebergang"
                ),
                "arbeitszeit": _arbeitszeit("formel.arbeitsmenge"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Walze", "walze")],
                KA.LOHN: [_lohn("Walzenfahrer")],
            },
        ),
    ),
    # --- Oberboden andecken (no compaction; hand or grader) ---
    "OBERBODEN_HAND": Vorgang(
        code="V_OBERBODEN_HAND",
        name="Oberboden liefern und andecken (Kolonne)",
        ausfuehrungsart=AA["KOLONNE"],
        rechnung=R(
            instanzen={
                "flaeche": _i(
                    "F_FLAECHE_VOLUMEN",
                    variable="flaeche_m2",
                    volumen="kontext.volumen_m3",
                    dicke="kontext.schichtdicke_m",
                ),
                "leistung": _leistung(
                    "stammdaten.oberboden_andeck_hand_m2_pro_h",
                    erschwernisfaktor="kontext.erschwernisfaktor",
                ),
                "arbeitszeit": _arbeitszeit("formel.flaeche"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Oberboden",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.LOHN: [_lohn("Andeckkolonne", "kontext.anzahl_arbeiter")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Oberboden antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    "OBERBODEN_GRADER": Vorgang(
        code="V_OBERBODEN_GRADER",
        name="Oberboden liefern und andecken (Grader)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        rechnung=R(
            instanzen={
                "flaeche": _i(
                    "F_FLAECHE_VOLUMEN",
                    variable="flaeche_m2",
                    volumen="kontext.volumen_m3",
                    dicke="kontext.schichtdicke_m",
                ),
                "leistung": _leistung("stammdaten.oberboden_andeck_grader_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("formel.flaeche"),
                "tonnage": _tonnage_schuettgut(),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Oberboden",
                        "formel.tonnage",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Grader", "grader")],
                KA.LOHN: [_lohn("Graderfahrer")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Oberboden antransportieren",
                        "formel.tonnage",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    # --- Unterlage reinigen (sweeper vs high-pressure wash-vacuum) ---
    "REINIGEN_KEHREN": Vorgang(
        code="V_REINIGEN_KEHREN",
        name="Unterlage reinigen (selbstaufn. Kehrmaschine)",
        ausfuehrungsart=AA["KEHRMASCHINE"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.kehr_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MASCHINE: [_maschine("Kehrmaschine", "kehrmaschine")],
                KA.LOHN: [_lohn("Bediener")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Kehrgut verwerten",
                        "kontext.flaeche_m2",
                        "stammdaten.ent_kehrgut_eur_pro_m2",
                    )
                ],
            },
        ),
    ),
    "REINIGEN_HD": Vorgang(
        code="V_REINIGEN_HD",
        name="Unterlage reinigen (Hochdruck-Wasch-Sauganlage)",
        ausfuehrungsart=AA["HD_WASCHSAUG"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.hd_reinigung_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MASCHINE: [_maschine("HD-Wasch-Sauganlage", "hd_waschsaug")],
                KA.LOHN: [_lohn("Reinigungskolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Waschschlamm verwerten",
                        "kontext.flaeche_m2",
                        "stammdaten.ent_waschschlamm_eur_pro_m2",
                    )
                ],
            },
        ),
    ),
    # --- Anspritzen / Schichtenverbund (one recipe, rate+binder per position) ---
    "ANSPRITZEN": Vorgang(
        code="V_ANSPRITZEN",
        name="Bitumenemulsion aufsprühen (Schichtenverbund)",
        ausfuehrungsart=AA["SPRITZGERAET"],
        rechnung=R(
            instanzen={
                "menge": _i(
                    "F_MENGE_ANSATZ",
                    einheiten={"ansatz": "t/m2"},
                    ansatz="kontext.bindemittelmenge_kg_pro_m2",
                    bezugsmenge="kontext.flaeche_m2",
                ),
                "leistung": _leistung("stammdaten.anspritz_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Bitumenemulsion",
                        "formel.menge",
                        "stammdaten.materialpreis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Rampenspritzgerät", "spritzgeraet")],
                KA.LOHN: [_lohn("Bediener")],
            },
        ),
    ),
    # --- Feinfräsen: Kaltfräse, eigene (gedeckelte) Präzisionsleistung ---
    "FEINFRAESEN": Vorgang(
        code="V_FEINFRAESEN",
        name="Asphalt feinfräsen",
        ausfuehrungsart=AA["KALTFRAESE"],
        rechnung=R(
            instanzen={
                "leistung": _i(
                    "F_LEISTUNG_TIEFE",
                    tiefenkonstante="10",
                    obergrenze="250",
                    tiefe="kontext.tiefe_cm",
                    erschwernisfaktor="kontext.erschwernisfaktor",
                ),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
                **_fraesgut(),
            },
            kosten={
                KA.MASCHINE: [_maschine("Kaltfräse (Feinfräsen)", "kaltfraese")],
                KA.LOHN: [_lohn("Fräskolonne", "kontext.anzahl_arbeiter")],
                KA.ENTSORGUNG: [
                    _kosten(
                        "Fräsgut entsorgen/verwerten",
                        "formel.tonnage",
                        "formel.entsorgungssatz",
                    )
                ],
                KA.ABTRANSPORT: [
                    _transport(
                        "Fräsgut zur Deponie",
                        "formel.tonnage",
                        "kontext.entfernung_deponie_km",
                    )
                ],
            },
        ),
    ),
    # --- Asphalt-Handeinbau (Kleinflächen): Kolonne + kleine Walze ---
    "ASPHALT_HAND": Vorgang(
        code="V_ASPHALT_HAND",
        name="Asphaltschicht im Handeinbau einbauen",
        ausfuehrungsart=AA["ASPHALT_HAND"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.handeinbau_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
                **_asphalt_menge("kontext.einbaudicke_cm"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Asphaltmischgut",
                        "formel.menge",
                        "stammdaten.asphalt_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [_maschine("Walze (klein)", "walze")],
                KA.LOHN: [_lohn("Handeinbaukolonne", "stammdaten.handeinbau_kolonne")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Mischgut antransportieren",
                        "formel.menge",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    # --- Gussasphalt (MA): Fertiger/Kocher, keine Verdichtung ---
    "GUSSASPHALT": Vorgang(
        code="V_GUSSASPHALT",
        name="Gussasphaltschicht einbauen",
        ausfuehrungsart=AA["GUSSASPHALT"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.gussasphalt_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
                **_asphalt_menge("kontext.einbaudicke_cm"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Gussasphaltmischgut",
                        "formel.menge",
                        "stammdaten.gussasphalt_preis_eur_pro_t",
                    )
                ],
                KA.MASCHINE: [
                    _maschine(
                        "Gussasphaltfertiger/Kocher",
                        "gussasphalt_geraet",
                        verbrauch="stammdaten.gussasphalt_l_pro_h",
                    )
                ],
                KA.LOHN: [_lohn("Einbaukolonne", "stammdaten.gussasphalt_kolonne")],
                KA.ANTRANSPORT: [
                    _transport(
                        "Mischgut antransportieren",
                        "formel.menge",
                        "kontext.entfernung_lieferant_km",
                    )
                ],
            },
        ),
    ),
    # --- DSK (Dünnschichtbelag im Kalteinbau / Slurry) ---
    "DSK": Vorgang(
        code="V_DSK",
        name="Dünnschichtbelag (DSK) einbauen",
        ausfuehrungsart=AA["DSK"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.dsk_leistung_m2_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.flaeche_m2"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "DSK-Mischgut",
                        "kontext.flaeche_m2",
                        "stammdaten.dsk_material_eur_pro_m2",
                    )
                ],
                KA.MASCHINE: [
                    _maschine(
                        "DSK-Fertiger", "dsk_geraet", verbrauch="stammdaten.dsk_l_pro_h"
                    )
                ],
                KA.LOHN: [_lohn("Einbaukolonne", "stammdaten.dsk_kolonne")],
            },
        ),
    ),
    # --- Randabdichtung/Nahtabdichtung (Dichtband/-masse), kl. Gerät + Kolonne ---
    "RANDABDICHTUNG": Vorgang(
        code="V_RANDABDICHTUNG",
        name="Randabdichtung/Nahtabdichtung herstellen",
        ausfuehrungsart=AA["FUGENGERAET"],
        rechnung=R(
            instanzen={
                "leistung": _leistung("stammdaten.randabdichtung_leistung_m_pro_h"),
                "arbeitszeit": _arbeitszeit("kontext.laenge_m"),
            },
            kosten={
                KA.MATERIAL: [
                    _kosten(
                        "Fugenband/Randmasse",
                        "kontext.laenge_m",
                        "stammdaten.randabdichtung_material_eur_pro_m",
                    )
                ],
                KA.MASCHINE: [
                    _maschine(
                        "Applikator/Heizgerät",
                        "randabdichtung_geraet",
                        verbrauch="stammdaten.randabdichtung_l_pro_h",
                    )
                ],
                KA.LOHN: [_lohn("Abdichtkolonne", "2")],
            },
        ),
    ),
}


# --------------------------------------------------------------------------- # Machine
# binding (applied to the Vorgänge above): which productivity profile each operation
# reads (betriebsart_code; the profile overrides the "leistung" instanz) and
# which Stammdaten rate variables a bound machine's property bag fills (kosten_bindung:
# rate variable -> property key). Centralised here so a re-wire is one table, not 36
# constructors. Composite/manual operations bind productivity only (their lumped/labour
# rates stay org-default).
def _kb(satz: str, lh: str) -> dict[str, str]:
    return {satz: "betriebskosten_eur_pro_h", lh: "kraftstoff_l_pro_h"}


_BINDUNGEN: dict[str, tuple[str, dict[str, str]]] = {
    "BODENABTRAG": ("boden_abtragen", _kb("bagger_stundensatz_eur", "bagger_l_pro_h")),
    "MARKIERUNG": (
        "demark_farbe",
        _kb("markfraese_stundensatz_eur", "markfraese_l_pro_h"),
    ),
    "SCHNEIDEN": (
        "asphalt_schneiden",
        _kb("schneider_stundensatz_eur", "schneider_l_pro_h"),
    ),
    "FRAESEN": (
        "regelfraesen",
        _kb("kaltfraese_stundensatz_eur", "kaltfraese_l_pro_h"),
    ),
    "AUFBRECHEN": (
        "asphalt_aufbrechen",
        _kb("aufbruch_stundensatz_eur", "aufbruch_l_pro_h"),
    ),
    "VERDICHTEN": ("verdichten_flaeche", _kb("walze_stundensatz_eur", "walze_l_pro_h")),
    "ASPHALT_EINBAU": (
        "asphalt_einbau",
        {"asphalt_zug_geraet_eur_pro_h": "betriebskosten_eur_pro_h"},
    ),
    "FSS_LEGEN": (
        "schuettgut_einbau",
        _kb("radlader_stundensatz_eur", "radlader_l_pro_h"),
    ),
    "FSS_PROFIL": ("profilieren", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "FSS_VERDICHTEN": (
        "verdichten_uebergang",
        _kb("walze_stundensatz_eur", "walze_l_pro_h"),
    ),
    "FSS_FERTIGER": (
        "schuettgut_einbau",
        _kb("fertiger_stundensatz_eur", "fertiger_l_pro_h"),
    ),
    "BANKETT_LEGEN": (
        "schuettgut_einbau",
        _kb("radlader_stundensatz_eur", "radlader_l_pro_h"),
    ),
    "BANKETT_PROFIL": ("profilieren", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "BANKETT_VERDICHTEN": (
        "bankett_verdichten",
        _kb("bankettwalze_stundensatz_eur", "bankettwalze_l_pro_h"),
    ),
    "BANKETT_FERTIGER": (
        "bankett_einbau",
        _kb("bankettfertiger_stundensatz_eur", "bankettfertiger_l_pro_h"),
    ),
    "BODEN_GROBK_LEGEN": (
        "schuettgut_einbau",
        _kb("radlader_stundensatz_eur", "radlader_l_pro_h"),
    ),
    "BODEN_GROBK_PROFIL": (
        "profilieren",
        _kb("grader_stundensatz_eur", "grader_l_pro_h"),
    ),
    "BODEN_GROBK_VERDICHTEN": (
        "verdichten_uebergang",
        _kb("walze_stundensatz_eur", "walze_l_pro_h"),
    ),
    "OBERBODEN_GRADER": (
        "oberboden_andecken",
        _kb("grader_stundensatz_eur", "grader_l_pro_h"),
    ),
    "REINIGEN_KEHREN": (
        "kehren",
        _kb("kehrmaschine_stundensatz_eur", "kehrmaschine_l_pro_h"),
    ),
    "REINIGEN_HD": (
        "hochdruckreinigen",
        _kb("hd_waschsaug_stundensatz_eur", "hd_waschsaug_l_pro_h"),
    ),
    "ANSPRITZEN": (
        "anspritzen",
        _kb("spritzgeraet_stundensatz_eur", "spritzgeraet_l_pro_h"),
    ),
    "ABSTUMPFEN": ("abstreuen", _kb("abstreuer_stundensatz_eur", "abstreuer_l_pro_h")),
    "NAHT_AUFWEITEN": (
        "fuge_aufweiten",
        _kb("schneider_stundensatz_eur", "schneider_l_pro_h"),
    ),
    "FUGENFUELLUNG": (
        "fugenverguss",
        _kb("fugen_geraet_stundensatz_eur", "fugen_geraet_l_pro_h"),
    ),
    "NAHT": (
        "naht_herstellen",
        _kb("naht_geraet_stundensatz_eur", "naht_geraet_l_pro_h"),
    ),
    # gap closers
    "FEINFRAESEN": (
        "feinfraesen",
        _kb("kaltfraese_stundensatz_eur", "kaltfraese_l_pro_h"),
    ),
    "GUSSASPHALT": (
        "gussasphalt_einbau",
        _kb("gussasphalt_geraet_stundensatz_eur", "gussasphalt_l_pro_h"),
    ),
    "DSK": ("dsk_einbau", _kb("dsk_geraet_stundensatz_eur", "dsk_l_pro_h")),
    "RANDABDICHTUNG": (
        "randabdichtung",
        _kb("randabdichtung_geraet_stundensatz_eur", "randabdichtung_l_pro_h"),
    ),
    # composite/manual: productivity only (lumped/labour rates stay org-default)
    "EINBAU": ("schuettgut_einbau", {}),
    "PLANUM": ("planum_herstellen", {}),
    "ASPHALT_HAND": ("asphalt_handeinbau", {}),
}

for _code, (_ba, _kbind) in _BINDUNGEN.items():
    _v = VORGAENGE[_code]
    _v.betriebsart_code = _ba
    _v.leistung_instanz = "leistung"
    _v.kosten_bindung = _kbind
