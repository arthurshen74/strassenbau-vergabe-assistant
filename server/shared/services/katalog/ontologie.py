"""
ontologie.py — the compiler's ontology: the static structure that tells the
Rezept-Compiler where
inputs live, plus the structural formula identity that stops it from re-inventing a base
formula.

Two halves (REZEPT_REDESIGN_PLAN §2.5), single-sourced here so the validator, the lookup
tool and
the Handbuch never drift:

- **Static structure** — the binding-path grammar (§2.2: which prefixes exist, which
Baustoff fields
  are addressable), the canonical unit set (§2.3), and the sanctioned dimension-changing
  conversions
  (the Mengengerüst formulas) the compiler chains instead of inventing arithmetic.
- **Structural formula identity** — `kanonische_form` canonicalises a DSL expression up
to
  parameter renaming and commutative/associative reordering, so a candidate formula that
  is
  isomorphic to an existing base formula is detected and rejected ("instantiate F_X,
  don't invent").

The dynamic half of the ontology — the described formulas/variables themselves — is the
catalog
rows (their Phase-3 `beschreibung`); the lookup tool retrieves over that prose. No
parallel ontology
document exists: the catalog IS the ontology body.
"""

from __future__ import annotations

import ast

from shared.services.kalkulation_v2.model import BAUSTOFF_PFAD_EINHEITEN, Formel

# --------------------------------------------------------------------------- #
# Static structure — the binding-path grammar (§2.2)
# --------------------------------------------------------------------------- #
# The legal source-path prefixes a FormelInstanz binding may use, with the meaning the
# compiler
# needs. A binding value is `<prefix>.<name>` for these prefixes, or a bare numeric
# literal. The
# machine seams (Leistungsprofil override, property-bag rates) ride the Vorgang's
# leistung_instanz /
# kosten_bindung, NOT a binding path — so they are not prefixes here.
BINDUNGS_PRAEFIXE: dict[str, str] = {
    "kontext": "Per-Position-Eingaben (Geometrie, Tiefe, Erschwernisfaktor, "
    "Kolonnenstärke) — "
    "situativ je LV-Position aufgelöst.",
    "stammdaten": "Katalog-Sätze/Konstanten (Löhne, Kraftstoff, "
    "Transport-/Entsorgungssätze, "
    "Leistungsansätze, EV2-Anker) und Brücken auf Baustoff-Felder.",
    "baustoff": "Felder des gebundenen Baustoffs: "
    + ", ".join(sorted(BAUSTOFF_PFAD_EINHEITEN))
    + ".",
    "formel": "Ergebnis einer anderen Instanz desselben Vorgangs "
    "(formel.<instanz-name>).",
}

# The addressable Baustoff fields (re-exported so the tool/Handbuch cite one source).
BAUSTOFF_FELDER: dict[str, str | None] = dict(BAUSTOFF_PFAD_EINHEITEN)

# Canonical unit vocabulary (§2.3) — expressions are written in exactly these; the
# converter scales
# a bound source whose einheit differs by scale only (cm→m), and refuses a dimension
# change.
KANONISCHE_EINHEITEN: tuple[str, ...] = (
    "m",
    "m2",
    "m3",
    "t",
    "h",
    "€",
    "St",
    "l",
    "km",
    "%",
    "-",
)

# The sanctioned dimension-CHANGING conversions (§2.3): never a unit conversion — a
# Mengengerüst
# formula the compiler chains. Maps "von-Dimension -> nach-Dimension" to the base
# formula that does it.
MENGENGERUEST_FORMELN: dict[str, str] = {
    "m3 -> t": "F_MENGE_VOLUMEN",
    "m2 -> m3": "F_VOLUMEN_FLAECHE",
    "m3 -> m2": "F_FLAECHE_VOLUMEN",
    "m·m·m -> m3": "F_VOLUMEN_QUADER",
    "E -> t (Ansatz)": "F_MENGE_ANSATZ",
}


# --------------------------------------------------------------------------- #
# Structural formula identity (§4 structural dedup)
# --------------------------------------------------------------------------- #
_KOMMUTATIV = (ast.Add, ast.Mult)
_KOMMUTATIV_OP = {ast.Add: "+", ast.Mult: "*"}


def _flatten(node: ast.AST, op_type: type) -> list[ast.AST]:
    """Flatten a chain of one associative-commutative operator into its operand
    multiset."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, op_type):
        return _flatten(node.left, op_type) + _flatten(node.right, op_type)
    return [node]


def _shape_key(node: ast.AST) -> str:
    """A parameter-AGNOSTIC structural signature (every Name -> 'P'), used only to order
    the operands
    of a commutative operator deterministically before parameters are re-indexed."""
    if isinstance(node, ast.Expression):
        return _shape_key(node.body)
    if isinstance(node, ast.Name):
        return "P"
    if isinstance(node, ast.Constant):
        return f"C{node.value!r}"
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op in _KOMMUTATIV:
            teile = sorted(_shape_key(o) for o in _flatten(node, op))
            return f"({_KOMMUTATIV_OP[op]}{''.join(teile)})"
        return f"({_shape_key(node.left)}{op.__name__}{_shape_key(node.right)})"
    if isinstance(node, ast.UnaryOp):
        return f"U{type(node.op).__name__}({_shape_key(node.operand)})"
    if isinstance(node, ast.Compare):
        return (
            f"Cmp{type(node.ops[0]).__name__}("
            f"{_shape_key(node.left)},{_shape_key(node.comparators[0])})"
        )
    if isinstance(node, ast.BoolOp):
        teile = sorted(_shape_key(v) for v in node.values)
        return f"B{type(node.op).__name__}({','.join(teile)})"
    if isinstance(node, ast.IfExp):
        return (
            f"If({_shape_key(node.test)};"
            f"{_shape_key(node.body)};{_shape_key(node.orelse)})"
        )
    if isinstance(node, ast.Call):
        return f"{node.func.id}({','.join(_shape_key(a) for a in node.args)})"  # type: ignore[attr-defined]
    return "?"


def _canon(node: ast.AST, idx: dict[str, str]) -> str:
    """Serialize `node` to a canonical string, assigning each parameter a placeholder
    (p0, p1, …) by
    first occurrence in canonical traversal order. Commutative operands are sorted by
    their
    param-agnostic shape first, so renaming + reordering collapse to one form.
    Re-indexing preserves
    parameter EQUALITY (a·a ≠ a·b), so a genuinely different formula is never wrongly
    matched."""
    if isinstance(node, ast.Expression):
        return _canon(node.body, idx)
    if isinstance(node, ast.Name):
        if node.id not in idx:
            idx[node.id] = f"p{len(idx)}"
        return idx[node.id]
    if isinstance(node, ast.Constant):
        return f"C{node.value!r}"
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op in _KOMMUTATIV:
            operanden = sorted(_flatten(node, op), key=_shape_key)
            return (
                f"({_KOMMUTATIV_OP[op]} {' '.join(_canon(o, idx) for o in operanden)})"
            )
        return f"({op.__name__} {_canon(node.left, idx)} {_canon(node.right, idx)})"
    if isinstance(node, ast.UnaryOp):
        return f"(U{type(node.op).__name__} {_canon(node.operand, idx)})"
    if isinstance(node, ast.Compare):
        return (
            f"(Cmp{type(node.ops[0]).__name__} "
            f"{_canon(node.left, idx)} {_canon(node.comparators[0], idx)})"
        )
    if isinstance(node, ast.BoolOp):
        teile = [_canon(v, idx) for v in node.values]
        return f"(B{type(node.op).__name__} {' '.join(teile)})"
    if isinstance(node, ast.IfExp):
        return (
            f"(If {_canon(node.test, idx)} {_canon(node.body, idx)} "
            f"{_canon(node.orelse, idx)})"
        )
    if isinstance(node, ast.Call):
        return f"({node.func.id} {' '.join(_canon(a, idx) for a in node.args)})"  # type: ignore[attr-defined]
    return "?"


def kanonische_form(ausdruck: str) -> str | None:
    """Canonical form of a DSL expression, invariant under parameter renaming and
    commutative/associative reordering. Two expressions share it iff they are
    structurally
    isomorphic. None on a parse error (the caller reports the syntax error
    separately)."""
    try:
        baum = ast.parse(ausdruck, mode="eval")
    except SyntaxError:
        return None
    return _canon(baum, {})


def basis_kanonformen(formeln: dict[str, Formel]) -> dict[str, list[str]]:
    """canonical form -> the base-formula names sharing it. Several base formulas are
    deliberately
    the same SHAPE (e.g. F_KOSTEN_SATZ / F_VOLUMEN_FLAECHE / F_MENGE_ANSATZ are all
    `a·b`); they
    differ by meaning and units, not structure — which is exactly why a candidate of
    that shape must
    INSTANTIATE one of them rather than mint a new one."""
    formen: dict[str, list[str]] = {}
    for name in sorted(formeln):
        kanon = kanonische_form(formeln[name].ausdruck)
        if kanon is not None:
            formen.setdefault(kanon, []).append(name)
    return formen


def isomorphe_basis(ausdruck: str, basis_formen: dict[str, list[str]]) -> list[str]:
    """The base formulas structurally isomorphic to `ausdruck` (empty if none).
    `basis_formen` comes
    from `basis_kanonformen`. A single Name or bare literal has no meaningful shape (it
    is not a
    computation), so it never matches — only a real expression can be a redundant
    re-invention."""
    kanon = kanonische_form(ausdruck)
    if kanon is None or not kanon.startswith(
        "("
    ):  # atoms (a bare name/const) are not formulas
        return []
    return basis_formen.get(kanon, [])
