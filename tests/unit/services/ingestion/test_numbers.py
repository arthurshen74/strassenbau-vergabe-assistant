from __future__ import annotations

from decimal import Decimal

import pytest

from shared.services.ingestion.numbers import parse_german_decimal


@pytest.mark.parametrize(
    "token,expected",
    [
        ("25,00", Decimal("25.00")),
        ("2.400,00", Decimal("2400.00")),
        ("1.234.567,89", Decimal("1234567.89")),
        ("0,5", Decimal("0.5")),
        ("7", Decimal("7")),
        (" 12,5 ", Decimal("12.5")),
    ],
)
def test_parses_german_format(token: str, expected: Decimal) -> None:
    assert parse_german_decimal(token) == expected


@pytest.mark.parametrize("token", ["", "abc", "1,2,3,abc", "m²"])
def test_rejects_garbage(token: str) -> None:
    with pytest.raises(ValueError):
        parse_german_decimal(token)
