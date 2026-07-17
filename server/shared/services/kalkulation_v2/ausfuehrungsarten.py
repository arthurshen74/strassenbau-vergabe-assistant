"""
ausfuehrungsarten.py — reusable Ausführungsarten (the 'how': manner of execution).

Each names a machine/crew configuration. Vorgänge reference these by key. Exports
AUSFUEHRUNGSARTEN (key -> Ausführungsart).
"""

from shared.services.kalkulation_v2.model import Ausführungsart

AUSFUEHRUNGSARTEN: dict[str, Ausführungsart] = {
    "BAGGER": Ausführungsart(
        code="AA_BAGGER", name="maschinell – Bagger", geraetebezug="Bagger"
    ),
    "RADLADER": Ausführungsart(
        code="AA_RADLADER_WALZE",
        name="maschinell – Radlader + Walze",
        geraetebezug="Radlader; Walze",
    ),
    "KALTFRAESE": Ausführungsart(
        code="AA_KALTFRAESE", name="maschinell – Kaltfräse", geraetebezug="Kaltfräse"
    ),
    "SCHNEIDER": Ausführungsart(
        code="AA_SCHNEIDER",
        name="maschinell – Fugenschneider",
        geraetebezug="Fugenschneider",
    ),
    "MARKFRAESE": Ausführungsart(
        code="AA_MARKFRAESE",
        name="maschinell – Demarkierung (Fräse/Hochdruck/Strahl)",
        geraetebezug="Demarkierungsgerät",
    ),
    "KOLONNE": Ausführungsart(
        code="AA_KOLONNE", name="manuell – Kolonne", geraetebezug="Kolonne"
    ),
    "GRADER": Ausführungsart(
        code="AA_GRADER",
        name="maschinell – Grader + Walze",
        geraetebezug="Grader; Walze",
    ),
    "RADLADER_SOLO": Ausführungsart(
        code="AA_RADLADER", name="maschinell – Radlader", geraetebezug="Radlader"
    ),
    "GRADER_SOLO": Ausführungsart(
        code="AA_GRADER_SOLO", name="maschinell – Grader", geraetebezug="Grader"
    ),
    "FERTIGER": Ausführungsart(
        code="AA_FERTIGER", name="maschinell – Fertiger", geraetebezug="Fertiger"
    ),
    "BANKETTWALZE": Ausführungsart(
        code="AA_BANKETTWALZE",
        name="maschinell – kleine Tandemwalze (Bankett)",
        geraetebezug="Tandemwalze klein",
    ),
    "BANKETT_FERTIGER": Ausführungsart(
        code="AA_BANKETT_FERTIGER",
        name="maschinell – Bankettfertiger",
        geraetebezug="Bankettfertiger",
    ),
    "KEHRMASCHINE": Ausführungsart(
        code="AA_KEHRMASCHINE",
        name="maschinell – selbstaufnehmende Kehrmaschine",
        geraetebezug="Kehrmaschine",
    ),
    "HD_WASCHSAUG": Ausführungsart(
        code="AA_HD_WASCHSAUG",
        name="maschinell – Hochdruck-Wasch-Sauganlage (≥2,30 m)",
        geraetebezug="HD-Wasch-Sauganlage",
    ),
    "SPRITZGERAET": Ausführungsart(
        code="AA_SPRITZGERAET",
        name="maschinell – Rampenspritzgerät",
        geraetebezug="Rampenspritzgerät",
    ),
    "ASPHALT_FERTIGER": Ausführungsart(
        code="AA_ASPHALT_FERTIGER",
        name="maschinell – Fertiger + Beschicker + Walzen",
        geraetebezug="Asphaltfertiger; Beschicker; Walzen",
    ),
    "GRID_KOLONNE": Ausführungsart(
        code="AA_GRID_KOLONNE",
        name="manuell – Fachkolonne Asphalteinlage",
        geraetebezug="Verlegekolonne",
    ),
    "ABSTREUER": Ausführungsart(
        code="AA_ABSTREUER",
        name="maschinell – Splittstreuer + Walze",
        geraetebezug="Abstreugerät; Walze",
    ),
    "FUGENGERAET": Ausführungsart(
        code="AA_FUGENGERAET",
        name="maschinell – Fugenvergussgerät",
        geraetebezug="Fugenkocher/-vergussgerät",
    ),
    "WALZE": Ausführungsart(
        code="AA_WALZE", name="maschinell – Walze", geraetebezug="Walze"
    ),
    "ASPHALT_HAND": Ausführungsart(
        code="AA_ASPHALT_HAND",
        name="manuell – Handeinbau + Walze",
        geraetebezug="Kolonne; Walze",
    ),
    "GUSSASPHALT": Ausführungsart(
        code="AA_GUSSASPHALT",
        name="maschinell – Gussasphalt-Fertiger/Bohle + Kocher",
        geraetebezug="Gussasphaltfertiger; Kocher",
    ),
    "DSK": Ausführungsart(
        code="AA_DSK",
        name="maschinell – DSK-/Slurry-Einbaumaschine",
        geraetebezug="DSK-Fertiger",
    ),
}
