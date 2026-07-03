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
    Kostenart,
    Leistung,
    VariableDefinition,
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
        aufloesung=[AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=Decimal("1"))],
    )


def test_rule1_unbekannte_variable_in_formel() -> None:
    bundle = KatalogBundle(
        formeln=[Formel(name="f1", ergebnis_variable="f1", ausdruck="a + b", einheit="€")]
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("unbekannte Variable" in f for f in bericht.fehler)


def test_rule1_unbekannte_funktion_nennt_whitelist() -> None:
    """The Rule-1 split: an unknown Call target is a *function* error naming the DSL whitelist,
    not a phantom variable (§7)."""
    bundle = KatalogBundle(
        formeln=[Formel(name="f1", ergebnis_variable="f1", ausdruck="interpoliere(a)", einheit="€")]
    )
    stand = KatalogStand(known_var_namen={"a"}, produzierbare_namen={"a"})
    bericht = pruefe_bundle(bundle, stand)
    assert not bericht.gueltig
    assert any(
        "unbekannte Funktion 'interpoliere'" in f and "abs" in f and "round" in f
        for f in bericht.fehler
    )
    # The bare `a` is a known variable, so it must NOT surface as an unknown-variable error.
    assert not any("unbekannte Variable" in f for f in bericht.fehler)


def test_rule2_formelzyklus() -> None:
    bundle = KatalogBundle(
        formeln=[
            Formel(name="f1", ergebnis_variable="f1", ausdruck="f2 + 1", einheit="€"),
            Formel(name="f2", ergebnis_variable="f2", ausdruck="f1 + 1", einheit="€"),
        ]
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("Formelzyklus" in f for f in bericht.fehler)


def test_rule3_kostenvariable_nicht_produzierbar() -> None:
    bundle = KatalogBundle(
        vorgaenge=[
            BundleVorgang(code="V_X", name="x", kostenvariablen={Kostenart.MATERIAL: "ghost"})
        ]
    )
    bericht = pruefe_bundle(bundle, KatalogStand())
    assert not bericht.gueltig
    assert any("nicht produzierbar" in f for f in bericht.fehler)


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
        var_gruppen={"X": {VariablenGruppe.FORMEL}},
    )
    bundle = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("X"))]
    )
    bericht = pruefe_bundle(bundle, stand)
    assert not bericht.gueltig
    assert any("neue Gruppen-Kollision" in f for f in bericht.fehler)


def test_rule5_update_einer_bestehenden_paarung_ist_erlaubt() -> None:
    """The fixtures deliberately shadow a stammdaten KONSTANTE with a Formel
    (entsorgung_fraesasphalt_eur_pro_t); updating either side of that existing pairing must
    validate — only a NEW pairing is a collision."""
    stand = KatalogStand(
        known_var_namen={"X"},
        produzierbare_namen={"X"},
        var_gruppen={"X": {VariablenGruppe.STAMMDATEN, VariablenGruppe.FORMEL}},
    )
    als_stammdaten = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=_konstante("X"))]
    )
    als_formel = KatalogBundle(
        formeln=[Formel(name="X", ergebnis_variable="X", ausdruck="2", einheit="€")]
    )
    assert pruefe_bundle(als_stammdaten, stand).gueltig, pruefe_bundle(als_stammdaten, stand).fehler
    assert pruefe_bundle(als_formel, stand).gueltig, pruefe_bundle(als_formel, stand).fehler


def test_rule5_neue_paarung_innerhalb_des_bundles_ist_fehler() -> None:
    bundle = KatalogBundle(
        variablen=[BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=_konstante("X"))],
        formeln=[Formel(name="X", ergebnis_variable="X", ausdruck="2", einheit="€")],
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
    """A self-contained recipe: a Vorgang whose cost variable is a bundle Formel, wired into a
    Bauverfahren and a Leistung mapping, all referencing an in-bundle Ausführungsart."""
    from shared.models.katalog import BundleBauverfahren
    from shared.services.kalkulation_v2.model import Ausführungsart

    bundle = KatalogBundle(
        leistungen=[Leistung(code="L_NEU", name="Neu", einheit="m2")],
        ausfuehrungsarten=[Ausführungsart(code="AA_NEU", name="Neu")],
        formeln=[Formel(name="kosten_neu", ergebnis_variable="kosten_neu", ausdruck="10", einheit="€")],
        vorgaenge=[
            BundleVorgang(
                code="V_NEU",
                name="Neu",
                ausfuehrungsart_code="AA_NEU",
                kostenvariablen={Kostenart.MATERIAL: "kosten_neu"},
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
