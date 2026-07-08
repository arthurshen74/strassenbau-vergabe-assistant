"""Unit tests for the bundle validator (§7 rules) — one failing fixture per rule, plus a
happy-path bundle. `pruefe_bundle` is pure, so each test builds a `KatalogStand` directly."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from shared.models.katalog import (
    BundleLieferant,
    BundlePreis,
    BundleVariable,
    BundleVorgang,
    KatalogBundle,
    KatalogEntitaet,
    VariablenGruppe,
)
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    AufloesungsSchritt,
    Formel,
    FormelInstanz,
    FormelParameter,
    Kostenart,
    Leistung,
    VariableDefinition,
    VorgangRechnung,
)
from shared.services.katalog.validierung import (
    KatalogStand,
    pruefe_aenderungsfelder,
    pruefe_bundle,
)


def _konstante(name: str) -> VariableDefinition:
    return VariableDefinition(
        name=name,
        bezeichnung=name,
        beschreibung=f"Testsatz {name} je Einheit (Fixture).",
        aufloesung=[AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=Decimal("1"))],
    )


def _formel(name: str, ausdruck: str, *parameter: str) -> Formel:
    return Formel(
        name=name, ausdruck=ausdruck, einheit="€", beschreibung=f"Testformel {name}.",
        parameter=[FormelParameter(name=p, beschreibung=f"Eingang {p}.") for p in parameter],
    )


def test_rule1_undeklarierter_parameter_in_formel() -> None:
    bundle = KatalogBundle(formeln=[_formel("f1", "a + b", "a")])
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("undeklarierten Parameter: b" in f for f in bericht.fehler)


def test_rule1_unbenutzter_parameter_in_formel() -> None:
    bundle = KatalogBundle(formeln=[_formel("f1", "a + 1", "a", "b")])
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("nicht verwendet: b" in f for f in bericht.fehler)


def test_rule1_unbekannte_funktion_nennt_whitelist() -> None:
    """The Rule-1 split: an unknown Call target is a *function* error naming the DSL whitelist,
    not a phantom parameter (§7)."""
    bundle = KatalogBundle(formeln=[_formel("f1", "interpoliere(a)", "a")])
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any(
        "unbekannte Funktion 'interpoliere'" in f and "abs" in f and "round" in f
        for f in bericht.fehler
    )
    # The bare `a` is a declared parameter, so it must NOT surface as undeclared.
    assert not any("undeklarierten Parameter" in f for f in bericht.fehler)


def test_rule1_fehlende_beschreibung() -> None:
    """Mandatory prose: a formula and each parameter carry a beschreibung."""
    kahl = Formel(name="f1", ausdruck="a + 1", einheit="€",
                  parameter=[FormelParameter(name="a")])
    bericht = pruefe_bundle(KatalogBundle(formeln=[kahl]), KatalogStand())
    assert not bericht.gueltig
    assert any("Formel 'f1': beschreibung fehlt" in f for f in bericht.fehler)
    assert any("Parameter 'a' ohne beschreibung" in f for f in bericht.fehler)


def test_rule1b_variable_ohne_beschreibung() -> None:
    """Mandatory prose (§2.6): a bundle variable without beschreibung is rejected; with it, valid."""
    kahl = VariableDefinition(
        name="satz_x", bezeichnung="Satz X",
        aufloesung=[AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=Decimal("1"))],
    )
    bundle = KatalogBundle(variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=kahl)])
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("satz_x" in f and "beschreibung fehlt" in f for f in bericht.fehler)

    mit_prosa = kahl.model_copy(update={"beschreibung": "Ein Testsatz je Tonne."})
    bundle2 = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=mit_prosa)]
    )
    assert pruefe_bundle(bundle2, KatalogStand()).gueltig


def test_rule2_instanz_zyklus() -> None:
    bundle = KatalogBundle(
        formeln=[_formel("F_X", "p", "p")],
        vorgaenge=[BundleVorgang(code="V_X", name="x", rechnung=VorgangRechnung(
            instanzen={
                "a": FormelInstanz(formel="F_X", bindung={"p": "formel.b"}),
                "b": FormelInstanz(formel="F_X", bindung={"p": "formel.a"}),
            }))],
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("Instanz-Zyklus" in f for f in bericht.fehler)


def test_rule2_bindung_unbekannt_oder_nicht_produzierbar() -> None:
    stand = KatalogStand(
        known_var_namen={"nur_hitl"},
        formeln={"F_X": _formel("F_X", "p", "p")},
    )

    def _vorgang(pfad: str) -> KatalogBundle:
        return KatalogBundle(vorgaenge=[BundleVorgang(code="V_X", name="x",
            rechnung=VorgangRechnung(kosten={
                Kostenart.MATERIAL: [FormelInstanz(formel="F_X", bindung={"p": pfad})],
            }))])

    bericht = pruefe_bundle(_vorgang("stammdaten.ghost"), stand)
    assert not bericht.gueltig
    assert any("unbekannte Variable 'stammdaten.ghost'" in f for f in bericht.fehler)

    bericht = pruefe_bundle(_vorgang("stammdaten.nur_hitl"), stand)
    assert not bericht.gueltig
    assert any("nicht produzierbar" in f for f in bericht.fehler)

    bericht = pruefe_bundle(_vorgang("quatsch"), stand)
    assert not bericht.gueltig
    assert any("unbekannter Bindungspfad 'quatsch'" in f for f in bericht.fehler)


def test_rule2_ungebundener_parameter_ohne_standard() -> None:
    stand = KatalogStand(formeln={"F_X": _formel("F_X", "p + q", "p", "q")})
    bundle = KatalogBundle(vorgaenge=[BundleVorgang(code="V_X", name="x",
        rechnung=VorgangRechnung(kosten={
            Kostenart.MATERIAL: [FormelInstanz(formel="F_X", bindung={"p": "1"})],
        }))])
    bericht = pruefe_bundle(bundle, stand)
    assert not bericht.gueltig
    assert any("Parameter 'q' ist ungebunden" in f for f in bericht.fehler)


def test_rule1_strukturelle_wiedererfindung_abgelehnt() -> None:
    """§4 dedup: a candidate isomorphic to an active base formula is rejected; a new shape passes."""
    stand = KatalogStand(formeln={"F_KOSTEN_SATZ": _formel("F_KOSTEN_SATZ", "menge * satz", "menge", "satz")})
    doppelt = KatalogBundle(formeln=[_formel("F_FLAECHE", "laenge * breite", "laenge", "breite")])
    bericht = pruefe_bundle(doppelt, stand)
    assert not bericht.gueltig
    assert any("strukturell identisch" in f and "F_KOSTEN_SATZ" in f for f in bericht.fehler)

    # Editing the base formula itself (same name) is NOT flagged as a re-invention.
    update = KatalogBundle(formeln=[_formel("F_KOSTEN_SATZ", "menge * satz", "menge", "satz")])
    assert pruefe_bundle(update, stand).gueltig, pruefe_bundle(update, stand).fehler


def test_rule2_einheit_dimensionswechsel_abgelehnt() -> None:
    """§2.5 einheit compatibility: binding a €/t source to a t/m³ parameter is a dimension mismatch
    (a Mengengerüst formula's job, not a binding) — rejected."""
    stand = KatalogStand(
        known_var_namen={"preis_eur_pro_t"},
        produzierbare_namen={"preis_eur_pro_t"},
        var_einheiten={"preis_eur_pro_t": "€/t"},
        formeln={"F_DICHTE": Formel(
            name="F_DICHTE", ausdruck="d", einheit="t", beschreibung="Test.",
            parameter=[FormelParameter(name="d", einheit="t/m3", beschreibung="Dichte.")],
        )},
    )
    bundle = KatalogBundle(vorgaenge=[BundleVorgang(code="V_X", name="x",
        rechnung=VorgangRechnung(kosten={
            Kostenart.MATERIAL: [FormelInstanz(formel="F_DICHTE", bindung={"d": "stammdaten.preis_eur_pro_t"})],
        }))])
    bericht = pruefe_bundle(bundle, stand)
    assert not bericht.gueltig
    assert any("passt nicht zum Parameter" in f and "preis_eur_pro_t" in f for f in bericht.fehler)


def test_rule2_skalierbare_einheit_ist_ok() -> None:
    """A dimension-PRESERVING mismatch (cm vs m) is bindable — the converter scales it."""
    stand = KatalogStand(
        known_var_namen={"tiefe_cm"}, produzierbare_namen={"tiefe_cm"},
        var_einheiten={"tiefe_cm": "cm"},
        formeln={"F_V": Formel(
            name="F_V", ausdruck="flaeche * dicke", einheit="m3", beschreibung="Test.",
            parameter=[FormelParameter(name="flaeche", beschreibung="F."),
                       FormelParameter(name="dicke", einheit="m", beschreibung="D.")],
        )},
    )
    bundle = KatalogBundle(vorgaenge=[BundleVorgang(code="V_X", name="x",
        rechnung=VorgangRechnung(kosten={
            Kostenart.MATERIAL: [FormelInstanz(formel="F_V", bindung={"flaeche": "5", "dicke": "kontext.tiefe_cm"})],
        }))])
    # tiefe_cm is a kontext var (produzierbar); cm→m is dimension-preserving, so no einheit error.
    fehler = [f for f in pruefe_bundle(bundle, stand).fehler if "passt nicht zum Parameter" in f]
    assert fehler == []


def test_rule4_unbekannte_ausfuehrungsart() -> None:
    bundle = KatalogBundle(
        vorgaenge=[BundleVorgang(code="V_X", name="x", ausfuehrungsart_code="AA_MISSING")]
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("unbekannte Ausführungsart" in f for f in bericht.fehler)


def test_rule5_variable_schattet_andere_gruppe() -> None:
    stand = KatalogStand(
        known_var_namen={"X"},
        produzierbare_namen={"X"},
        var_gruppen={"X": {VariablenGruppe.KONTEXT}},
    )
    bundle = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("X"))]
    )
    bericht = pruefe_bundle(bundle, stand)
    assert not bericht.gueltig
    assert any("neue Gruppen-Kollision" in f for f in bericht.fehler)


def test_rule5_update_einer_bestehenden_paarung_ist_erlaubt() -> None:
    """Updating either side of an EXISTING cross-gruppe pairing must validate — only a NEW
    pairing is a collision (grandfathered dual-gruppe names stay editable)."""
    stand = KatalogStand(
        known_var_namen={"X"},
        produzierbare_namen={"X"},
        var_gruppen={"X": {VariablenGruppe.STAMMDATEN, VariablenGruppe.KONTEXT}},
    )
    als_stammdaten = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("X"))]
    )
    als_kontext = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=_konstante("X"))]
    )
    assert pruefe_bundle(als_stammdaten, stand).gueltig, pruefe_bundle(als_stammdaten, stand).fehler
    assert pruefe_bundle(als_kontext, stand).gueltig, pruefe_bundle(als_kontext, stand).fehler


def test_rule5_neue_paarung_innerhalb_des_bundles_ist_fehler() -> None:
    bundle = KatalogBundle(
        variablen=[
            BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=_konstante("X")),
            BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("X")),
        ],
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("neue Gruppen-Kollision" in f for f in bericht.fehler)


def test_rule6_supersede_ist_kein_fehler() -> None:
    stand = KatalogStand(leistung_codes={"L_X"})
    bundle = KatalogBundle(leistungen=[Leistung(code="L_X", name="X", einheit="m2")])
    bericht = pruefe_bundle(bundle, stand)
    assert bericht.gueltig
    assert any("L_X" in a and "aktualisiert" in a for a in bericht.aktualisierungen)


def test_gueltiges_bundle_ohne_fehler() -> None:
    """A self-contained recipe: a Vorgang whose cost line instantiates a bundle base formula
    over bundle variables, wired into a Bauverfahren and a Leistung mapping, all referencing
    an in-bundle Ausführungsart."""
    from shared.models.katalog import BundleBauverfahren
    from shared.services.kalkulation_v2.model import Ausführungsart

    bundle = KatalogBundle(
        leistungen=[Leistung(code="L_NEU", name="Neu", einheit="m2")],
        ausfuehrungsarten=[Ausführungsart(code="AA_NEU", name="Neu")],
        formeln=[_formel("F_NEU", "menge * satz", "menge", "satz")],
        variablen=[
            BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=_konstante("flaeche_neu")),
            BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("satz_neu")),
        ],
        vorgaenge=[
            BundleVorgang(
                code="V_NEU",
                name="Neu",
                ausfuehrungsart_code="AA_NEU",
                rechnung=VorgangRechnung(kosten={
                    Kostenart.MATERIAL: [FormelInstanz(
                        formel="F_NEU",
                        bindung={"menge": "kontext.flaeche_neu", "satz": "stammdaten.satz_neu"},
                    )],
                }),
            )
        ],
        bauverfahren=[BundleBauverfahren(code="BV_NEU", name="Neu", vorgang_codes=["V_NEU"])],
        leistung_bauverfahren={"L_NEU": ["BV_NEU"]},
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert bericht.gueltig, bericht.fehler


def test_rule7_preis_unbekannter_lieferant() -> None:
    bundle = KatalogBundle(
        preise=[
            BundlePreis(
                lieferant_code="LIEF_GHOST",
                baustoff_code="B_GHOST",
                preis_eur_pro_t=Decimal("10"),
                gueltig_ab=date(2026, 1, 1),
            )
        ]
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("unbekannter Lieferant" in f for f in bericht.fehler)
    assert any("unbekannter Baustoff" in f for f in bericht.fehler)


def test_rule7_preis_referenziert_bundle_lieferant_und_baustoff() -> None:
    """A price may reference a Lieferant/Baustoff created in the same bundle (active ∪ bundle)."""
    from shared.services.kalkulation_v2.model import Baustoff

    bundle = KatalogBundle(
        lieferanten=[BundleLieferant(code="LIEF_NEU", name="Neu")],
        baustoffe=[
            Baustoff(code="B_NEU", name="Neu", rohdichte_t_pro_m3=Decimal("2.4"), einheit="t")
        ],
        preise=[
            BundlePreis(
                lieferant_code="LIEF_NEU",
                baustoff_code="B_NEU",
                preis_eur_pro_t=Decimal("15.90"),
                gueltig_ab=date(2026, 8, 1),
            )
        ],
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert bericht.gueltig, bericht.fehler


def test_rule8_preis_validitaet_und_positiv() -> None:
    stand = KatalogStand(lieferanten_codes={"LIEF_X"}, baustoff_codes={"B_X"})
    verdreht = KatalogBundle(
        preise=[
            BundlePreis(
                lieferant_code="LIEF_X",
                baustoff_code="B_X",
                preis_eur_pro_t=Decimal("10"),
                gueltig_ab=date(2026, 2, 1),
                gueltig_bis=date(2026, 1, 1),
            )
        ]
    )
    bericht = pruefe_bundle(verdreht, stand)
    assert not bericht.gueltig and any("gueltig_ab" in f and "gueltig_bis" in f for f in bericht.fehler)

    nicht_positiv = KatalogBundle(
        preise=[
            BundlePreis(
                lieferant_code="LIEF_X",
                baustoff_code="B_X",
                preis_eur_pro_t=Decimal("0"),
                gueltig_ab=date(2026, 1, 1),
            )
        ]
    )
    bericht = pruefe_bundle(nicht_positiv, stand)
    assert not bericht.gueltig and any("muss > 0" in f for f in bericht.fehler)


def test_rule9_aenderungsfeld_whitelist() -> None:
    fehler = pruefe_aenderungsfelder(
        KatalogEntitaet.BAUSTOFFE, {"basispreis_eur_pro_t": Decimal("16.20"), "quatsch": 1}
    )
    assert any("quatsch" in f and "basispreis_eur_pro_t" in f for f in fehler)
    # A clean delta touching only payload columns passes.
    assert pruefe_aenderungsfelder(KatalogEntitaet.BAUSTOFFE, {"kategorie": "Asphaltmischgut"}) == []
