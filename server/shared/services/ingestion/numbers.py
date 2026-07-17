"""German number parsing for LV quantities.

LV `menge` tokens are printed in German convention: '.' groups thousands and ',' is the
decimal separator (e.g. '2.400,00' is two thousand four hundred). We normalise to a
`Decimal` for the `menge` column (Numeric(12, 4))."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

THOUSANDS_SEP = "."
DECIMAL_SEP = ","
DECIMAL_POINT = "."
PLACEHOLDER_FILL = "x"


def parse_german_decimal(token: str) -> Decimal:
    """Parse a German-formatted quantity token into a Decimal. Raises ValueError on
    garbage."""
    normalised = (
        token.strip().replace(THOUSANDS_SEP, "").replace(DECIMAL_SEP, DECIMAL_POINT)
    )
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise ValueError(f"not a German decimal: {token!r}") from exc


def is_placeholder_menge(token: str) -> bool:
    """True when a menge token is a blank LV form placeholder (e.g. 'xxxxxx,xx').

    A template position prints its unfilled quantity as a run of 'x' fill in German
    number shape -- the digits are simply not entered yet. That is document content, not
    a bad segmentation, so it reads as a missing quantity rather than an unparseable
    one."""
    digits = token.strip().replace(THOUSANDS_SEP, "").replace(DECIMAL_SEP, "")
    return bool(digits) and all(char in PLACEHOLDER_FILL for char in digits.lower())
