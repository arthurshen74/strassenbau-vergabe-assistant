"""
ausfuehrungsarten.py — reusable Ausführungsarten (the 'how': manner of execution).

Each names a machine/crew configuration. Vorgänge reference these by key.
Exports AUSFUEHRUNGSARTEN (key -> Ausführungsart).
"""

from model import Ausführungsart

AUSFUEHRUNGSARTEN: dict[str, Ausführungsart] = {
    "BAGGER":       Ausführungsart(code="AA_BAGGER", name="maschinell – Bagger", geraetebezug="Bagger"),
    "RADLADER":     Ausführungsart(code="AA_RADLADER_WALZE", name="maschinell – Radlader + Walze", geraetebezug="Radlader; Walze"),
    "KALTFRAESE":   Ausführungsart(code="AA_KALTFRAESE", name="maschinell – Kaltfräse", geraetebezug="Kaltfräse"),
    "SCHNEIDER":    Ausführungsart(code="AA_SCHNEIDER", name="maschinell – Fugenschneider", geraetebezug="Fugenschneider"),
    "MARKFRAESE":   Ausführungsart(code="AA_MARKFRAESE", name="maschinell – Markierungsfräse", geraetebezug="Markierungsfräse"),
    "KOLONNE":      Ausführungsart(code="AA_KOLONNE", name="manuell – Kolonne", geraetebezug="Kolonne"),
    "GRADER":       Ausführungsart(code="AA_GRADER", name="maschinell – Grader + Walze", geraetebezug="Grader; Walze"),
    "WALZE":        Ausführungsart(code="AA_WALZE", name="maschinell – Walze", geraetebezug="Walze"),
    "ASPHALT_HAND": Ausführungsart(code="AA_ASPHALT_HAND", name="manuell – Handeinbau + Walze", geraetebezug="Kolonne; Walze"),
}