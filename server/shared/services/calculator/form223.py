"""VHB Formblatt 223-style EP-Aufgliederung from the costed operation lines.

Built deterministically after the Kalkulator approves: every cost line's EUR is
bucketed by its formula's Kostenart (FORMULA_KOSTENART), the crew lines' labor
hours sum to the Zeitansatz, and everything is divided by the position's Menge
to give per-Mengeneinheit values (ohne Umsatzsteuer).
"""

from __future__ import annotations

from shared.services.calculator.formulas import FORMULA_KOSTENART
from shared.services.calculator.models import Form223Row, Kostenart


def build_form_223_row(position: dict, operation_results: list[dict]) -> Form223Row:
    menge = position["boq_menge"]
    totals = {kostenart: 0.0 for kostenart in Kostenart}
    labor_hours = 0.0
    for op in operation_results:
        for line in op["lines"]:
            if line["eur"] is None:
                continue
            totals[FORMULA_KOSTENART[line["formula"]]] += line["eur"]
            labor_hours += line.get("labor_h") or 0.0
    return Form223Row(
        oz=position["oz"],
        kurzbezeichnung=position["kurztext"],
        menge=menge,
        mengeneinheit=position["boq_einheit"],
        zeitansatz_h=round(labor_hours / menge, 3),
        lohn_eur=round(totals[Kostenart.LOHN] / menge, 2),
        stoffe_eur=round(totals[Kostenart.STOFFE] / menge, 2),
        geraete_eur=round(totals[Kostenart.GERAETE] / menge, 2),
        sonstiges_eur=round(totals[Kostenart.SONSTIGES] / menge, 2),
    )
