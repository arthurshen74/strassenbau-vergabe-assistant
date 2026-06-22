"""
vorgaenge.py — reusable Vorgänge (discrete work operations).

Each Vorgang binds an Ausführungsart and maps each relevant Kostenart to the
name of the formula-variable that yields that cost line. Exports VORGAENGE.
"""

from model import Kostenart as KA, Vorgang
from ausfuehrungsarten import AUSFUEHRUNGSARTEN as AA

VORGAENGE: dict[str, Vorgang] = {
    "BODENABTRAG": Vorgang(code="V_BODENABTRAG", name="Boden/Bankett abtragen und schälen",
        ausfuehrungsart=AA["BAGGER"],
        kostenvariablen={KA.MASCHINE: "mk_bagger", KA.LOHN: "lohn_bagger",
                         KA.ENTSORGUNG: "ent_boden", KA.ABTRANSPORT: "trans_boden"}),
    "EINBAU": Vorgang(code="V_EINBAU", name="Baustoff liefern, einbauen und verdichten",
        ausfuehrungsart=AA["RADLADER"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_einbau",
                         KA.LOHN: "lohn_einbau", KA.ANTRANSPORT: "trans_material"}),
    "ERSCHWERNIS": Vorgang(code="V_ERSCHWERNIS", name="Erschwernis-Zulage (Einfassungen)",
        ausfuehrungsart=AA["KOLONNE"], kostenvariablen={KA.LOHN: "lohn_erschwernis"}),
    "MARKIERUNG": Vorgang(code="V_MARKIERUNG", name="Markierung entfernen",
        ausfuehrungsart=AA["MARKFRAESE"],
        kostenvariablen={KA.MASCHINE: "mk_markierung", KA.LOHN: "lohn_markierung"}),
    "SCHNEIDEN": Vorgang(code="V_SCHNEIDEN", name="Asphaltbefestigung trennen/schneiden",
        ausfuehrungsart=AA["SCHNEIDER"],
        kostenvariablen={KA.MASCHINE: "mk_schnitt", KA.LOHN: "lohn_schnitt"}),
    "FRAESEN": Vorgang(code="V_FRAESEN", name="Asphalt fräsen",
        ausfuehrungsart=AA["KALTFRAESE"],
        kostenvariablen={KA.MASCHINE: "mk_fraese", KA.LOHN: "lohn_fraese",
                         KA.ENTSORGUNG: "ent_fraesgut", KA.ABTRANSPORT: "trans_fraesgut"}),
    "AUFBRECHEN": Vorgang(code="V_AUFBRECHEN", name="Asphalt aufbrechen und aufnehmen",
        ausfuehrungsart=AA["BAGGER"],
        kostenvariablen={KA.MASCHINE: "mk_aufbruch", KA.LOHN: "lohn_aufbruch",
                         KA.ENTSORGUNG: "ent_aufbruch", KA.ABTRANSPORT: "trans_aufbruch"}),
    "PLANUM": Vorgang(code="V_PLANUM", name="Planum herstellen",
        ausfuehrungsart=AA["GRADER"],
        kostenvariablen={KA.MASCHINE: "mk_planum", KA.LOHN: "lohn_planum"}),
    "VERDICHTEN": Vorgang(code="V_VERDICHTEN", name="Boden verdichten",
        ausfuehrungsart=AA["WALZE"],
        kostenvariablen={KA.MASCHINE: "mk_verdichten", KA.LOHN: "lohn_verdichten"}),
    "ASPHALT_EINBAU": Vorgang(code="V_ASPHALT_EINBAU", name="Asphalttragschicht einbauen",
        ausfuehrungsart=AA["ASPHALT_HAND"],
        kostenvariablen={KA.MATERIAL: "materialkosten_asphalt", KA.MASCHINE: "mk_asphalt",
                         KA.LOHN: "lohn_asphalt", KA.ANTRANSPORT: "trans_asphalt"}),
    "NAHT": Vorgang(code="V_NAHT", name="Naht in Asphaltschicht herstellen",
        ausfuehrungsart=AA["KOLONNE"],
        kostenvariablen={KA.MATERIAL: "materialkosten_naht", KA.MASCHINE: "mk_naht",
                         KA.LOHN: "lohn_naht"}),
}