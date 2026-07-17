"""einheiten.py — the unit converter for formula bindings.

One small fixed table maps every supported unit to its canonical base and an EXACT
power-of-ten Decimal factor (REZEPT_REDESIGN_PLAN.md §2.3). Compound units are parsed as
products/quotients of base units ("kg/m2", "€/(t·km)", "g/(m·cm)"), their factor is the
quotient of the component factors — still exact, so a converted calculation stays
cent-identical to the inline-arithmetic formulas it replaces.

Conversion happens at binding time: a source value whose Einheit differs from the
parameter's canonical Einheit by scale only is multiplied by `faktor(von, nach)`.
Dimension CHANGES (m³→t) are never conversions — they are Mengengerüst formulas. Unknown
units pass through unchanged (save-time validation owns unit compatibility; the
calculator must not crash on a generic parameter like `menge`).
"""

from __future__ import annotations

from decimal import Decimal

# Base unit -> (canonical unit, exact Decimal factor). Only exact power-of-ten scalings
# — a unit that would need a repeating-decimal factor (min->h) has no place in this
# table.
_BASIS: dict[str, tuple[str, Decimal]] = {
    "mm": ("m", Decimal("0.001")),
    "cm": ("m", Decimal("0.01")),
    "m": ("m", Decimal("1")),
    "km": ("km", Decimal("1")),
    "mm2": ("m2", Decimal("0.000001")),
    "cm2": ("m2", Decimal("0.0001")),
    "m2": ("m2", Decimal("1")),
    "m3": ("m3", Decimal("1")),
    "g": ("t", Decimal("0.000001")),
    "kg": ("t", Decimal("0.001")),
    "t": ("t", Decimal("1")),
    "h": ("h", Decimal("1")),
    "l": ("l", Decimal("1")),
    "st": ("St", Decimal("1")),
    "€": ("€", Decimal("1")),
    "eur": ("€", Decimal("1")),
    "%": ("%", Decimal("1")),
}

_ERSATZ = str.maketrans({"²": "2", "³": "3", "*": "·", "x": "·"})


def _norm(einheit: str) -> str:
    return einheit.strip().translate(_ERSATZ).lower()


def _basis_faktor(token: str) -> tuple[str, Decimal] | None:
    return _BASIS.get(_norm(token))


def _produkt(teil: str) -> tuple[tuple[str, ...], Decimal] | None:
    """Parse a ·-product of base units -> (sorted canonical units, combined factor)."""
    kanonisch: list[str] = []
    faktor = Decimal("1")
    for token in teil.replace("(", "").replace(")", "").split("·"):
        basis = _basis_faktor(token)
        if basis is None:
            return None
        kanonisch.append(basis[0])
        faktor *= basis[1]
    return tuple(sorted(kanonisch)), faktor


def zerlege(
    einheit: str,
) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], Decimal] | None:
    """Decompose a unit into its canonical dimension signature and exact scale factor.

    Returns ((numerator units, denominator units), factor) or None for an unknown unit.
    "-" and "" are dimensionless (empty signature, factor 1).
    """
    norm = _norm(einheit)
    if norm in ("", "-", "–"):
        return ((), ()), Decimal("1")
    zaehler, _, nenner = norm.partition("/")
    oben = _produkt(zaehler)
    if oben is None:
        return None
    if not nenner:
        return (oben[0], ()), oben[1]
    unten = _produkt(nenner)
    if unten is None:
        return None
    return (oben[0], unten[0]), oben[1] / unten[1]


def faktor(von: str | None, nach: str | None) -> Decimal | None:
    """Exact conversion factor from `von` to `nach`, or None when no conversion applies
    (either unit missing/unknown, or already identical). Raises on a dimension mismatch
    between two KNOWN units — that is a mis-binding, not a conversion."""
    if von is None or nach is None or _norm(von) == _norm(nach):
        return None
    z_von, z_nach = zerlege(von), zerlege(nach)
    if z_von is None or z_nach is None:
        return None
    if z_von[0] != z_nach[0]:
        raise ValueError(f"Einheiten nicht skalierbar: '{von}' -> '{nach}'")
    f = z_von[1] / z_nach[1]
    return None if f == 1 else f


def konvertiere(wert: Decimal, von: str | None, nach: str | None) -> Decimal:
    f = faktor(von, nach)
    return wert if f is None else wert * f
