"""Tests for the compiler ontology (REZEPT_REDESIGN_PLAN §2.5, §4): the AST canonicalisation that
powers structural formula dedup, and the static path grammar."""

from __future__ import annotations

from shared.services.kalkulation_v2.formel import FORMELN
from shared.services.katalog.ontologie import (
    BINDUNGS_PRAEFIXE,
    basis_kanonformen,
    isomorphe_basis,
    kanonische_form,
)


def test_kanonform_invariant_unter_umbenennung_und_reihenfolge() -> None:
    # Renaming parameters and reordering commutative operands must not change the canonical form.
    assert kanonische_form("a * b") == kanonische_form("x * y") == kanonische_form("y * x")
    assert kanonische_form("stunden * (stundensatz + verbrauch * kraftstoffpreis) * anteil") == \
        kanonische_form("anteil * stunden * (kraftstoffpreis * verbrauch + stundensatz)")
    # Parameter EQUALITY is preserved: a·a is NOT the same shape as a·b.
    assert kanonische_form("a * a") != kanonische_form("a * b")


def test_kanonform_unterscheidet_operatoren() -> None:
    assert kanonische_form("a / b") != kanonische_form("a * b")
    assert kanonische_form("a + b") != kanonische_form("a - b")


def test_atom_hat_keine_formel_form() -> None:
    # A bare name / literal is not a computation, so it never matches a base formula.
    assert isomorphe_basis("menge", basis_kanonformen(FORMELN)) == []
    assert isomorphe_basis("42", basis_kanonformen(FORMELN)) == []


def test_isomorphe_basis_erkennt_wiedererfindung() -> None:
    formen = basis_kanonformen(FORMELN)
    # `a·b` is the shape of three base formulas — all must be offered, none invented.
    treffer = isomorphe_basis("menge_x * satz_x", formen)
    assert {"F_KOSTEN_SATZ", "F_VOLUMEN_FLAECHE", "F_MENGE_ANSATZ"} <= set(treffer)
    # F_MASCHINE's exact shape, renamed + reordered.
    assert "F_MASCHINE" in isomorphe_basis(
        "h * (satz + l * preis) * teil", formen
    )
    # A genuinely new shape matches nothing.
    assert isomorphe_basis("grundbetrag + zuschlag * menge", formen) == []


def test_jede_basisformel_findet_sich_selbst() -> None:
    formen = basis_kanonformen(FORMELN)
    for name, f in FORMELN.items():
        assert name in isomorphe_basis(f.ausdruck, formen)


def test_pfadgrammatik_deckt_die_praefixe() -> None:
    assert set(BINDUNGS_PRAEFIXE) == {"kontext", "stammdaten", "baustoff", "formel"}
