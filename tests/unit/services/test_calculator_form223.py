"""Tests for the VHB 223 EP-Aufgliederung builder."""

from __future__ import annotations

from shared.services.calculator.form223 import build_form_223_row

POSITION = {
    "oz": "01.01.0010",
    "kurztext": "Frostschutzschicht herstellen",
    "boq_menge": 50.0,
    "boq_einheit": "m3",
}

OPERATION_RESULTS = [
    {"operation": "supply_material", "lines": [
        {"formula": "material_cost", "eur": 1000.0, "labor_h": None},
        {"formula": "delivery_cost", "eur": 250.0, "labor_h": None},
    ]},
    {"operation": "distribute", "lines": [
        {"formula": "duration_by_performance", "eur": None, "labor_h": None},
        {"formula": "equipment_cost", "eur": 300.0, "labor_h": None},
        {"formula": "crew_cost", "eur": 420.0, "labor_h": 10.0},
        {"formula": "machine_mobilization", "eur": 100.0, "labor_h": None},
    ]},
]


def test_buckets_by_kostenart_and_divides_by_menge():
    row = build_form_223_row(POSITION, OPERATION_RESULTS)

    assert row.oz == "01.01.0010"
    assert row.kurzbezeichnung == "Frostschutzschicht herstellen"
    assert row.menge == 50.0
    assert row.mengeneinheit == "m3"
    assert row.lohn_eur == 8.40        # 420 / 50
    assert row.stoffe_eur == 20.00     # 1000 / 50
    assert row.geraete_eur == 8.00     # (300 + 100) / 50
    assert row.sonstiges_eur == 5.00   # 250 / 50
    assert row.zeitansatz_h == 0.2     # 10 crew-hours / 50


def test_value_rows_do_not_contribute():
    only_value_rows = [{"operation": "x", "lines": [
        {"formula": "duration_by_performance", "eur": None, "labor_h": None},
    ]}]
    row = build_form_223_row(POSITION, only_value_rows)
    assert (row.lohn_eur, row.stoffe_eur, row.geraete_eur, row.sonstiges_eur,
            row.zeitansatz_h) == (0.0, 0.0, 0.0, 0.0, 0.0)
