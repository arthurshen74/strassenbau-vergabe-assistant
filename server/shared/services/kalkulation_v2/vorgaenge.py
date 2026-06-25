"""
vorgaenge.py — reusable Vorgänge (discrete work operations).

Each Vorgang binds an Ausführungsart and maps each relevant Kostenart to the
name of the formula-variable that yields that cost line. Exports VORGAENGE.
"""

from shared.services.kalkulation_v2.model import Kostenart as KA, Vorgang
from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN as AA

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
    "MARKIERUNG": Vorgang(code="V_MARKIERUNG", name="Markierung entfernen (Demarkierung)",
        ausfuehrungsart=AA["MARKFRAESE"],
        kostenvariablen={KA.MASCHINE: "mk_markierung", KA.LOHN: "lohn_markierung",
                         KA.ENTSORGUNG: "ent_demark"}),
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
    "ASPHALT_EINBAU": Vorgang(code="V_ASPHALT_EINBAU", name="Asphaltschicht einbauen (Fertiger + Beschicker)",
        ausfuehrungsart=AA["ASPHALT_FERTIGER"],
        kostenvariablen={KA.MATERIAL: "materialkosten_asphalt", KA.MASCHINE: "mk_asphalt",
                         KA.LOHN: "lohn_asphalt", KA.ANTRANSPORT: "trans_asphalt"}),
    "GRID_EINBAU": Vorgang(code="V_GRID_EINBAU", name="Asphalteinlage liefern und verlegen",
        ausfuehrungsart=AA["GRID_KOLONNE"],
        kostenvariablen={KA.MATERIAL: "grid_materialkosten", KA.MASCHINE: "mk_grid", KA.LOHN: "lohn_grid"}),
    "ABSTUMPFEN": Vorgang(code="V_ABSTUMPFEN", name="Abstumpfung aufbringen und einwalzen",
        ausfuehrungsart=AA["ABSTREUER"],
        kostenvariablen={KA.MATERIAL: "mk_abstreu_material", KA.MASCHINE: "mk_abstreuen",
                         KA.LOHN: "lohn_abstreuen", KA.ENTSORGUNG: "ent_abstreu"}),
    "NAHT_AUFWEITEN": Vorgang(code="V_NAHT_AUFWEITEN", name="Naht/Anschluss zur Fuge aufweiten (schneiden)",
        ausfuehrungsart=AA["SCHNEIDER"],
        kostenvariablen={KA.MASCHINE: "mk_naht_aufweiten", KA.LOHN: "lohn_naht_aufweiten"}),
    "FUGENFUELLUNG": Vorgang(code="V_FUGENFUELLUNG", name="Fugenfüllung herstellen (Fugenmasse N2)",
        ausfuehrungsart=AA["FUGENGERAET"],
        kostenvariablen={KA.MATERIAL: "mk_fugenmasse", KA.MASCHINE: "mk_fugenfuellung", KA.LOHN: "lohn_fugenfuellung"}),
    "NAHT": Vorgang(code="V_NAHT", name="Naht in Asphaltschicht herstellen",
        ausfuehrungsart=AA["KOLONNE"],
        kostenvariablen={KA.MATERIAL: "materialkosten_naht", KA.MASCHINE: "mk_naht",
                         KA.LOHN: "lohn_naht"}),
    # --- FSS decomposition (lay / profile / compact) ---
    "FSS_LEGEN": Vorgang(code="V_FSS_LEGEN", name="FSS liefern und legen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_fss_legen",
                         KA.LOHN: "lohn_fss_legen", KA.ANTRANSPORT: "trans_material"}),
    "FSS_PROFIL": Vorgang(code="V_FSS_PROFIL", name="FSS profilieren (auf Höhe abziehen)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        kostenvariablen={KA.MASCHINE: "mk_fss_profil", KA.LOHN: "lohn_fss_profil"}),
    "FSS_VERDICHTEN": Vorgang(code="V_FSS_VERDICHTEN", name="FSS verdichten (Ev2-gerecht)",
        ausfuehrungsart=AA["WALZE"],
        kostenvariablen={KA.MASCHINE: "mk_fss_verdicht", KA.LOHN: "lohn_fss_verdicht"}),
    "FSS_FERTIGER": Vorgang(code="V_FSS_FERTIGER", name="FSS liefern, legen und abziehen (Fertiger)",
        ausfuehrungsart=AA["FERTIGER"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_fss_fertiger",
                         KA.LOHN: "lohn_fss_fertiger", KA.ANTRANSPORT: "trans_material"}),
    # --- Bankettbefestigung (lay / profile-to-Quergefälle / compact) ---
    "BANKETT_LEGEN": Vorgang(code="V_BANKETT_LEGEN", name="Bankettmaterial liefern und legen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_bankett_legen",
                         KA.LOHN: "lohn_bankett_legen", KA.ANTRANSPORT: "trans_material"}),
    "BANKETT_PROFIL": Vorgang(code="V_BANKETT_PROFIL", name="Bankett profilgerecht abziehen (Quergefälle)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        kostenvariablen={KA.MASCHINE: "mk_bankett_profil", KA.LOHN: "lohn_bankett_profil"}),
    "BANKETT_VERDICHTEN": Vorgang(code="V_BANKETT_VERDICHTEN", name="Bankett verdichten (Ev2 ≥ 70)",
        ausfuehrungsart=AA["BANKETTWALZE"],
        kostenvariablen={KA.MASCHINE: "mk_bankett_verdicht", KA.LOHN: "lohn_bankett_verdicht"}),
    "BANKETT_FERTIGER": Vorgang(code="V_BANKETT_FERTIGER", name="Bankett liefern, legen und profilieren (Fertiger)",
        ausfuehrungsart=AA["BANKETT_FERTIGER"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_bankett_fertiger",
                         KA.LOHN: "lohn_bankett_fertiger", KA.ANTRANSPORT: "trans_material"}),
    # --- Grobkörniger Boden (Auffüllung unter Banketten, Einzelflächen) ---
    "BODEN_GROBK_LEGEN": Vorgang(code="V_BODEN_GROBK_LEGEN", name="Grobkörnigen Boden liefern und einbauen",
        ausfuehrungsart=AA["RADLADER_SOLO"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_boden_legen",
                         KA.LOHN: "lohn_boden_legen", KA.ANTRANSPORT: "trans_material"}),
    "BODEN_GROBK_PROFIL": Vorgang(code="V_BODEN_GROBK_PROFIL", name="Profilgerecht herstellen (Planum einbegriffen)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        kostenvariablen={KA.MASCHINE: "mk_boden_profil", KA.LOHN: "lohn_boden_profil"}),
    "BODEN_GROBK_VERDICHTEN": Vorgang(code="V_BODEN_GROBK_VERDICHTEN", name="Boden verdichten (Standardverdichtung)",
        ausfuehrungsart=AA["WALZE"],
        kostenvariablen={KA.MASCHINE: "mk_boden_verdicht", KA.LOHN: "lohn_boden_verdicht"}),
    # --- Oberboden andecken (no compaction; hand or grader) ---
    "OBERBODEN_HAND": Vorgang(code="V_OBERBODEN_HAND", name="Oberboden liefern und andecken (Kolonne)",
        ausfuehrungsart=AA["KOLONNE"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.LOHN: "lohn_oberboden_hand",
                         KA.ANTRANSPORT: "trans_material"}),
    "OBERBODEN_GRADER": Vorgang(code="V_OBERBODEN_GRADER", name="Oberboden liefern und andecken (Grader)",
        ausfuehrungsart=AA["GRADER_SOLO"],
        kostenvariablen={KA.MATERIAL: "materialkosten", KA.MASCHINE: "mk_oberboden_grader",
                         KA.LOHN: "lohn_oberboden_grader", KA.ANTRANSPORT: "trans_material"}),
    # --- Unterlage reinigen (sweeper vs high-pressure wash-vacuum) ---
    "REINIGEN_KEHREN": Vorgang(code="V_REINIGEN_KEHREN", name="Unterlage reinigen (selbstaufn. Kehrmaschine)",
        ausfuehrungsart=AA["KEHRMASCHINE"],
        kostenvariablen={KA.MASCHINE: "mk_kehren", KA.LOHN: "lohn_kehren", KA.ENTSORGUNG: "ent_kehrgut"}),
    "REINIGEN_HD": Vorgang(code="V_REINIGEN_HD", name="Unterlage reinigen (Hochdruck-Wasch-Sauganlage)",
        ausfuehrungsart=AA["HD_WASCHSAUG"],
        kostenvariablen={KA.MASCHINE: "mk_hd_reinigung", KA.LOHN: "lohn_hd_reinigung", KA.ENTSORGUNG: "ent_waschschlamm"}),
    # --- Anspritzen / Schichtenverbund (one recipe, rate+binder per position) ---
    "ANSPRITZEN": Vorgang(code="V_ANSPRITZEN", name="Bitumenemulsion aufsprühen (Schichtenverbund)",
        ausfuehrungsart=AA["SPRITZGERAET"],
        kostenvariablen={KA.MATERIAL: "mk_bindemittel", KA.MASCHINE: "mk_anspritzen", KA.LOHN: "lohn_anspritzen"}),
    # --- Feinfräsen: Kaltfräse, eigene (langsamere) Leistung ---
    "FEINFRAESEN": Vorgang(code="V_FEINFRAESEN", name="Asphalt feinfräsen",
        ausfuehrungsart=AA["KALTFRAESE"],
        kostenvariablen={KA.MASCHINE: "mk_feinfraese", KA.LOHN: "lohn_feinfraese",
                         KA.ENTSORGUNG: "ent_fraesgut", KA.ABTRANSPORT: "trans_fraesgut"}),
    # --- Asphalt-Handeinbau (Kleinflächen): Kolonne + kleine Walze ---
    "ASPHALT_HAND": Vorgang(code="V_ASPHALT_HAND", name="Asphaltschicht im Handeinbau einbauen",
        ausfuehrungsart=AA["ASPHALT_HAND"],
        kostenvariablen={KA.MATERIAL: "materialkosten_asphalt", KA.MASCHINE: "mk_handeinbau",
                         KA.LOHN: "lohn_handeinbau", KA.ANTRANSPORT: "trans_asphalt"}),
    # --- Gussasphalt (MA): Fertiger/Kocher, keine Verdichtung ---
    "GUSSASPHALT": Vorgang(code="V_GUSSASPHALT", name="Gussasphaltschicht einbauen",
        ausfuehrungsart=AA["GUSSASPHALT"],
        kostenvariablen={KA.MATERIAL: "mk_gussasphalt_material", KA.MASCHINE: "mk_gussasphalt",
                         KA.LOHN: "lohn_gussasphalt", KA.ANTRANSPORT: "trans_asphalt"}),
    # --- DSK (Dünnschichtbelag im Kalteinbau / Slurry) ---
    "DSK": Vorgang(code="V_DSK", name="Dünnschichtbelag (DSK) einbauen",
        ausfuehrungsart=AA["DSK"],
        kostenvariablen={KA.MATERIAL: "mk_dsk_material", KA.MASCHINE: "mk_dsk", KA.LOHN: "lohn_dsk"}),
    # --- Randabdichtung/Nahtabdichtung (Dichtband/-masse), kl. Gerät + Kolonne ---
    "RANDABDICHTUNG": Vorgang(code="V_RANDABDICHTUNG", name="Randabdichtung/Nahtabdichtung herstellen",
        ausfuehrungsart=AA["FUGENGERAET"],
        kostenvariablen={KA.MATERIAL: "mk_randabdichtung_material", KA.MASCHINE: "mk_randabdichtung",
                         KA.LOHN: "lohn_randabdichtung"}),
}


# --------------------------------------------------------------------------- #
# Machine binding (applied to the Vorgänge above): which productivity profile each
# operation reads (betriebsart_code -> leistung_variable) and which cost variables a
# bound machine's property bag fills (kosten_bindung: cost_variable -> property key).
# Centralised here so a re-wire is one table, not 36 constructors. Composite/manual
# operations bind productivity only (their lumped/labour rates stay org-default).
def _kb(satz: str, lh: str) -> dict[str, str]:
    return {satz: "betriebskosten_eur_pro_h", lh: "kraftstoff_l_pro_h"}


_BINDUNGEN: dict[str, tuple[str, str, dict[str, str]]] = {
    "BODENABTRAG": ("boden_abtragen", "bagger_leistung_m3_pro_h", _kb("bagger_stundensatz_eur", "bagger_l_pro_h")),
    "MARKIERUNG": ("demark_farbe", "markierung_leistung_m_pro_h", _kb("markfraese_stundensatz_eur", "markfraese_l_pro_h")),
    "SCHNEIDEN": ("asphalt_schneiden", "schnitt_leistung_m_pro_h", _kb("schneider_stundensatz_eur", "schneider_l_pro_h")),
    "FRAESEN": ("regelfraesen", "fraese_leistung_m2_pro_h", _kb("kaltfraese_stundensatz_eur", "kaltfraese_l_pro_h")),
    "AUFBRECHEN": ("asphalt_aufbrechen", "aufbruch_leistung_m2_pro_h", _kb("aufbruch_stundensatz_eur", "aufbruch_l_pro_h")),
    "VERDICHTEN": ("verdichten_flaeche", "walze_leistung_m2_pro_h", _kb("walze_stundensatz_eur", "walze_l_pro_h")),
    "ASPHALT_EINBAU": ("asphalt_einbau", "asphalt_einbau_leistung_t_pro_h",
                       {"asphalt_zug_geraet_eur_pro_h": "betriebskosten_eur_pro_h"}),
    "FSS_LEGEN": ("schuettgut_einbau", "radlader_leistung_m3_pro_h", _kb("radlader_stundensatz_eur", "radlader_l_pro_h")),
    "FSS_PROFIL": ("profilieren", "profil_leistung_m2_pro_h", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "FSS_VERDICHTEN": ("verdichten_uebergang", "walze_uebergang_leistung_m2_pro_h", _kb("walze_stundensatz_eur", "walze_l_pro_h")),
    "FSS_FERTIGER": ("schuettgut_einbau", "fertiger_leistung_m2_pro_h", _kb("fertiger_stundensatz_eur", "fertiger_l_pro_h")),
    "BANKETT_LEGEN": ("schuettgut_einbau", "bankett_legen_leistung_m3_pro_h", _kb("radlader_stundensatz_eur", "radlader_l_pro_h")),
    "BANKETT_PROFIL": ("profilieren", "bankett_profil_leistung_m2_pro_h", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "BANKETT_VERDICHTEN": ("bankett_verdichten", "bankettwalze_uebergang_leistung_m2_pro_h",
                           _kb("bankettwalze_stundensatz_eur", "bankettwalze_l_pro_h")),
    "BANKETT_FERTIGER": ("bankett_einbau", "bankettfertiger_leistung_m2_pro_h",
                         _kb("bankettfertiger_stundensatz_eur", "bankettfertiger_l_pro_h")),
    "BODEN_GROBK_LEGEN": ("schuettgut_einbau", "boden_legen_leistung_m3_pro_h", _kb("radlader_stundensatz_eur", "radlader_l_pro_h")),
    "BODEN_GROBK_PROFIL": ("profilieren", "boden_profil_leistung_m2_pro_h", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "BODEN_GROBK_VERDICHTEN": ("verdichten_uebergang", "boden_verdicht_leistung_m2_pro_h_uebergang",
                               _kb("walze_stundensatz_eur", "walze_l_pro_h")),
    "OBERBODEN_GRADER": ("oberboden_andecken", "oberboden_andeck_grader_m2_pro_h", _kb("grader_stundensatz_eur", "grader_l_pro_h")),
    "REINIGEN_KEHREN": ("kehren", "kehr_leistung_m2_pro_h", _kb("kehrmaschine_stundensatz_eur", "kehrmaschine_l_pro_h")),
    "REINIGEN_HD": ("hochdruckreinigen", "hd_reinigung_leistung_m2_pro_h", _kb("hd_waschsaug_stundensatz_eur", "hd_waschsaug_l_pro_h")),
    "ANSPRITZEN": ("anspritzen", "anspritz_leistung_m2_pro_h", _kb("spritzgeraet_stundensatz_eur", "spritzgeraet_l_pro_h")),
    "ABSTUMPFEN": ("abstreuen", "abstreuen_leistung_m2_pro_h", _kb("abstreuer_stundensatz_eur", "abstreuer_l_pro_h")),
    "NAHT_AUFWEITEN": ("fuge_aufweiten", "naht_aufweiten_leistung_m_pro_h", _kb("schneider_stundensatz_eur", "schneider_l_pro_h")),
    "FUGENFUELLUNG": ("fugenverguss", "fugenfuellung_leistung_m_pro_h", _kb("fugen_geraet_stundensatz_eur", "fugen_geraet_l_pro_h")),
    "NAHT": ("naht_herstellen", "naht_leistung_m_pro_h", _kb("naht_geraet_stundensatz_eur", "naht_geraet_l_pro_h")),
    # gap closers
    "FEINFRAESEN": ("feinfraesen", "feinfraese_leistung_m2_pro_h", _kb("kaltfraese_stundensatz_eur", "kaltfraese_l_pro_h")),
    "GUSSASPHALT": ("gussasphalt_einbau", "gussasphalt_leistung_m2_pro_h", _kb("gussasphalt_geraet_stundensatz_eur", "gussasphalt_l_pro_h")),
    "DSK": ("dsk_einbau", "dsk_leistung_m2_pro_h", _kb("dsk_geraet_stundensatz_eur", "dsk_l_pro_h")),
    "RANDABDICHTUNG": ("randabdichtung", "randabdichtung_leistung_m_pro_h",
                       _kb("randabdichtung_geraet_stundensatz_eur", "randabdichtung_l_pro_h")),
    # composite/manual: productivity only (lumped/labour rates stay org-default)
    "EINBAU": ("schuettgut_einbau", "einbau_leistung_m3_pro_h", {}),
    "PLANUM": ("planum_herstellen", "planum_leistung_m2_pro_h", {}),
    "ASPHALT_HAND": ("asphalt_handeinbau", "handeinbau_leistung_m2_pro_h", {}),
}

for _code, (_ba, _lv, _kbind) in _BINDUNGEN.items():
    _v = VORGAENGE[_code]
    _v.betriebsart_code = _ba
    _v.leistung_variable = _lv
    _v.kosten_bindung = _kbind