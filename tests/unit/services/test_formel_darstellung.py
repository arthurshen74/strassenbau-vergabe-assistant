"""Snapshot tests for the DSL→LaTeX walker (§10.4).

A multi-input formula must render to a precedence-correct LaTeX string with a legend resolving each
short symbol to its variable, Bezeichnung and Einheit. Also covers the division (\\frac), the
whitelisted functions, and the ternary (nested \\begin{cases}).
"""

from __future__ import annotations

from shared.services.kalkulation_v2.formel_darstellung import (
    VariablenLegende,
    formel_zu_latex,
    stelle_formel_dar,
)


def test_mehrfach_input_formel_latex_und_legende() -> None:
    ausdruck = "fss_verdicht_stunden * (walze_stundensatz_eur + walze_l_pro_h * kraftstoffpreis_eur_pro_l)"
    info = {
        "fss_verdicht_stunden": VariablenLegende(bezeichnung="Verdichtungsstunden", einheit="h"),
        "walze_stundensatz_eur": VariablenLegende(bezeichnung="Walze Stundensatz", einheit="€/h"),
        "walze_l_pro_h": VariablenLegende(bezeichnung="Walze Verbrauch", einheit="l/h"),
        "kraftstoffpreis_eur_pro_l": VariablenLegende(bezeichnung="Dieselpreis", einheit="€/l"),
    }

    darstellung = stelle_formel_dar(ausdruck, info)

    assert darstellung.latex == r"x_{1} \cdot \left(x_{2} + x_{3} \cdot x_{4}\right)"
    assert [(e.symbol, e.variable, e.einheit) for e in darstellung.legende] == [
        ("x_{1}", "fss_verdicht_stunden", "h"),
        ("x_{2}", "walze_stundensatz_eur", "€/h"),
        ("x_{3}", "walze_l_pro_h", "l/h"),
        ("x_{4}", "kraftstoffpreis_eur_pro_l", "€/l"),
    ]
    assert darstellung.legende[3].bezeichnung == "Dieselpreis"


def test_division_wird_frac() -> None:
    assert formel_zu_latex(
        "volumen_m3 / schichtdicke_m", {"volumen_m3": "V", "schichtdicke_m": "d"}
    ) == r"\frac{V}{d}"


def test_funktionen_ceil_min_max() -> None:
    assert formel_zu_latex("ceil(schichtdicke_m / max_lagendicke_b2_m)") == (
        r"\left\lceil \frac{\mathrm{schichtdicke\_m}}{\mathrm{max\_lagendicke\_b2\_m}} \right\rceil"
    )
    assert formel_zu_latex("max(120, 1000 / tiefe_cm)", {"tiefe_cm": "t"}) == (
        r"\max\left(120,\ \frac{1000}{t}\right)"
    )


def test_subtraktion_klammert_rechte_summe() -> None:
    # a - (b + c) must keep the parentheses; a - b + c must not gain them.
    assert formel_zu_latex("a - (b + c)", {"a": "a", "b": "b", "c": "c"}) == r"a - \left(b + c\right)"
    assert formel_zu_latex("a - b + c", {"a": "a", "b": "b", "c": "c"}) == r"a - b + c"


def test_ternaer_wird_verschachtelte_cases() -> None:
    ausdruck = (
        "ent_fraesgut_verwertbar if fraesgut_klasse <= 1 else "
        "(ent_fraesgut_belastet if fraesgut_klasse <= 2 else ent_fraesgut_pechhaltig)"
    )
    darstellung = stelle_formel_dar(ausdruck)

    assert darstellung.latex.startswith(r"\begin{cases} x_{1} & \text{falls } x_{2} \le 1")
    assert r"\begin{cases} x_{3} & \text{falls } x_{2} \le 2 \\ x_{4} & \text{sonst} \end{cases}" in (
        darstellung.latex
    )
    # fraesgut_klasse appears once in the legend though it is referenced twice.
    assert [e.variable for e in darstellung.legende] == [
        "ent_fraesgut_verwertbar",
        "fraesgut_klasse",
        "ent_fraesgut_belastet",
        "ent_fraesgut_pechhaltig",
    ]
