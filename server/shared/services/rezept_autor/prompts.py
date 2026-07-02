"""Placeholder prompt + catalog index for the recipe-author's `entwerfen` node (Part B).

Deliberately minimal — the real prompt design is Part C. The system prompt instructs the model to
reuse existing Vorgänge/variables and to write `Formel.ausdruck` in the calculator DSL; the user
prompt appends the active-catalog index (Leistungen/Vorgänge/Variablen) as context plus any prior
validation errors or reviewer feedback.
"""

from __future__ import annotations

import json

from shared.services.kalkulation_v2 import leistungen as m_leist
from shared.services.kalkulation_v2 import store as m_store
from shared.services.kalkulation_v2 import vorgaenge as m_vorg

REZEPT_AUTOR_SYSTEM = (
    "Du bist ein Kalkulations-Rezept-Assistent für den Straßenbau. Aus einer Beschreibung in "
    "natürlicher Sprache entwirfst du ein RezeptBundle: eine Leistung, ein Bauverfahren, die "
    "nötigen Vorgänge, Formeln und Variablen sowie das Leistung→Bauverfahren-Mapping. "
    "Regeln: Verwende vorhandene Vorgänge, Ausführungsarten und Variablen wo möglich (referenziere "
    "sie per code/name). Schreibe Formel.ausdruck in der DSL (arithmetische Ausdrücke über "
    "Variablennamen; erlaubte Funktionen: abs, min, max, round, ceil, floor). Kostenvariablen eines "
    "Vorgangs müssen produzierbar sein (Formel/Konstante/Stammdaten oder eine kontext-Variable). "
    "Gib ausschließlich ein gültiges RezeptBundle zurück."
)


def katalog_index() -> dict:
    """A compact view of the active catalog the model may reuse (codes/names only)."""
    return {
        "leistungen": [{"code": c, "name": lg.name, "einheit": lg.einheit} for c, lg in m_leist.LEISTUNGEN.items()],
        "vorgaenge": [
            {"code": v.code, "name": v.name, "kostenvariablen": {k.value: n for k, n in v.kostenvariablen.items()}}
            for v in m_vorg.VORGAENGE.values()
        ],
        "variablen": sorted(m_store.KATALOG.keys()),
    }


def baue_user_prompt(beschreibung: str, fehler: list[str], feedback: str | None) -> str:
    teile = [f"Beschreibung des gewünschten Rezepts:\n{beschreibung}"]
    if feedback:
        teile.append(f"Feedback des Kalkulators (berücksichtigen):\n{feedback}")
    if fehler:
        teile.append("Validierungsfehler des letzten Entwurfs (beheben):\n- " + "\n- ".join(fehler))
    teile.append("Aktiver Katalog (zur Wiederverwendung):\n" + json.dumps(katalog_index(), ensure_ascii=False, indent=2, default=str))
    return "\n\n".join(teile)
