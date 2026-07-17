"""
formel_darstellung.py — render a DSL expression as LaTeX with a symbol legend.

A Formel's `ausdruck` is a restricted Python expression (the DSL of `model.py`). Long
German variable names (`kraftstoffpreis_eur_pro_l`) make the raw expression unreadable
as maths, so the catalog agent's `zeige_formel` tool (T26) shows it two ways: a LaTeX
rendering that substitutes a short symbol (x₁, x₂, …) for every referenced variable,
plus a legend resolving each symbol back to its variable name, Bezeichnung and Einheit.

The walker handles exactly the node types the evaluator (`eval_ausdruck`) accepts —
binary and unary arithmetic, power, comparisons, boolean ops, the ternary, and the
`_FUNKTIONEN` whitelist — and is precedence-aware so the parenthesisation matches the
expression's meaning. It is deterministic and pure (no I/O), so the rendering
snapshot-tests cleanly.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from shared.services.kalkulation_v2.model import _FUNKTIONEN

# Binding strength, loosest to tightest. A child is parenthesised when it binds looser
# than its position requires; `_wrap` compares against these.
_PREC_OR = 1
_PREC_AND = 2
_PREC_CMP = 3
_PREC_ADD = 4
_PREC_MUL = 5
_PREC_UNARY = 6
_PREC_POW = 7
_PREC_ATOM = 8

_BINOP_LATEX = {ast.Add: "+", ast.Sub: "-", ast.Mult: r"\cdot", ast.Mod: r"\bmod"}
_CMP_LATEX = {
    ast.Lt: "<",
    ast.LtE: r"\le",
    ast.Gt: ">",
    ast.GtE: r"\ge",
    ast.Eq: "=",
    ast.NotEq: r"\ne",
}


class VariablenLegende(BaseModel):
    """The human-readable metadata a legend entry resolves a symbol to (Bezeichnung +
    Einheit)."""

    model_config = ConfigDict(extra="forbid")

    bezeichnung: str | None = None
    einheit: str | None = None


class LegendenEintrag(BaseModel):
    """One legend row: the short LaTeX symbol, the DSL variable it stands for, and its
    metadata."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    variable: str
    bezeichnung: str | None = None
    einheit: str | None = None


class FormelDarstellung(BaseModel):
    """A rendered formula: the LaTeX body plus the legend for every symbol it uses."""

    model_config = ConfigDict(extra="forbid")

    latex: str
    legende: list[LegendenEintrag]


def _namen_in_reihenfolge(baum: ast.AST) -> list[str]:
    """Referenced variable names in source (left-to-right) order, function names
    excluded, deduped.

    Ordered by source position, not AST field order, so the ternary reads body→test→else
    as written rather than the `IfExp` node's test-first field order.
    """
    namen = [
        n for n in ast.walk(baum) if isinstance(n, ast.Name) and n.id not in _FUNKTIONEN
    ]
    namen.sort(key=lambda n: (n.lineno, n.col_offset))
    reihenfolge: list[str] = []
    gesehen: set[str] = set()
    for n in namen:
        if n.id not in gesehen:
            gesehen.add(n.id)
            reihenfolge.append(n.id)
    return reihenfolge


def kurz_symbole(namen: list[str]) -> dict[str, str]:
    """Assign each variable a short LaTeX symbol x₁, x₂, … in the given order."""
    return {name: f"x_{{{i}}}" for i, name in enumerate(namen, start=1)}


def _zahl(value: object) -> str:
    """Render a numeric constant without exponent noise or trailing zeros."""
    if isinstance(value, bool):
        return r"\text{wahr}" if value else r"\text{falsch}"
    if isinstance(value, float):
        value = Decimal(str(value))
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _symbol(name: str, symbole: Mapping[str, str]) -> str:
    if name in symbole:
        return symbole[name]
    return r"\mathrm{" + name.replace("_", r"\_") + "}"


def _wrap(gerendert: tuple[str, int], mindest: int) -> str:
    """Parenthesise a rendered child when it binds looser than its position allows."""
    latex, prec = gerendert
    return rf"\left({latex}\right)" if prec < mindest else latex


def _render(node: ast.AST, symbole: Mapping[str, str]) -> tuple[str, int]:
    """Render one node to (latex, precedence)."""
    if isinstance(node, ast.Expression):
        return _render(node.body, symbole)
    if isinstance(node, ast.Constant):
        return _zahl(node.value), _PREC_ATOM
    if isinstance(node, ast.Name):
        return _symbol(node.id, symbole), _PREC_ATOM
    if isinstance(node, ast.BinOp):
        return _render_binop(node, symbole)
    if isinstance(node, ast.UnaryOp):
        vorzeichen = "-" if isinstance(node.op, ast.USub) else "+"
        return (
            f"{vorzeichen}{_wrap(_render(node.operand, symbole), _PREC_UNARY)}",
            _PREC_UNARY,
        )
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        links = _wrap(_render(node.left, symbole), _PREC_CMP + 1)
        rechts = _wrap(_render(node.comparators[0], symbole), _PREC_CMP + 1)
        return f"{links} {_CMP_LATEX[type(node.ops[0])]} {rechts}", _PREC_CMP
    if isinstance(node, ast.BoolOp):
        prec = _PREC_AND if isinstance(node.op, ast.And) else _PREC_OR
        verbinder = r"\land" if isinstance(node.op, ast.And) else r"\lor"
        teile = [_wrap(_render(v, symbole), prec + 1) for v in node.values]
        return f" {verbinder} ".join(teile), prec
    if isinstance(node, ast.IfExp):
        body = _render(node.body, symbole)[0]
        test = _render(node.test, symbole)[0]
        orelse = _render(node.orelse, symbole)[0]
        cases = (
            rf"\begin{{cases}} {body} & \text{{falls }} {test} \\ {orelse} & "
            rf"\text{{sonst}} \end{{cases}}"
        )
        return cases, _PREC_ATOM
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _render_call(node, symbole), _PREC_ATOM
    raise ValueError(f"nicht darstellbarer Ausdruck: {ast.dump(node)}")


def _render_binop(node: ast.BinOp, symbole: Mapping[str, str]) -> tuple[str, int]:
    op = type(node.op)
    if op is ast.Div:
        zaehler = _render(node.left, symbole)[0]
        nenner = _render(node.right, symbole)[0]
        return rf"\frac{{{zaehler}}}{{{nenner}}}", _PREC_ATOM
    if op is ast.Pow:
        basis = _wrap(_render(node.left, symbole), _PREC_POW)
        exponent = _render(node.right, symbole)[0]
        return f"{basis}^{{{exponent}}}", _PREC_POW
    prec = _PREC_ADD if op in (ast.Add, ast.Sub) else _PREC_MUL
    # Right operand of the non-commutative subtraction binds one level tighter to force
    # a - (b + c).
    rechts_mindest = prec + 1 if op is ast.Sub else prec
    links = _wrap(_render(node.left, symbole), prec)
    rechts = _wrap(_render(node.right, symbole), rechts_mindest)
    return f"{links} {_BINOP_LATEX[op]} {rechts}", prec


def _render_call(node: ast.Call, symbole: Mapping[str, str]) -> str:
    name = node.func.id  # type: ignore[attr-defined]
    args = [_render(a, symbole)[0] for a in node.args]
    if name == "abs" and len(args) == 1:
        return rf"\left|{args[0]}\right|"
    if name == "ceil" and len(args) == 1:
        return rf"\left\lceil {args[0]} \right\rceil"
    if name == "floor" and len(args) == 1:
        return rf"\left\lfloor {args[0]} \right\rfloor"
    if name in ("min", "max"):
        return rf"\{name}\left({r',\ '.join(args)}\right)"
    return rf"\operatorname{{{name}}}\left({r',\ '.join(args)}\right)"


def formel_zu_latex(ausdruck: str, symbole: Mapping[str, str] | None = None) -> str:
    """Render a DSL expression to a LaTeX string, substituting `symbole` for variable
    names."""
    baum = ast.parse(ausdruck, mode="eval")
    return _render(baum, symbole or {})[0]


def stelle_formel_dar(
    ausdruck: str, info: Mapping[str, VariablenLegende] | None = None
) -> FormelDarstellung:
    """Render a formula with short symbols and a legend resolving each to its variable +
    metadata."""
    baum = ast.parse(ausdruck, mode="eval")
    namen = _namen_in_reihenfolge(baum)
    symbole = kurz_symbole(namen)
    latex = _render(baum, symbole)[0]
    info = info or {}
    legende = [
        LegendenEintrag(
            symbol=symbole[name],
            variable=name,
            bezeichnung=info[name].bezeichnung if name in info else None,
            einheit=info[name].einheit if name in info else None,
        )
        for name in namen
    ]
    return FormelDarstellung(latex=latex, legende=legende)
