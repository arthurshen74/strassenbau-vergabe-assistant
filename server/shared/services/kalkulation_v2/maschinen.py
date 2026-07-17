"""
maschinen.py — the machine fleet (master data) for mill-and-fill operations.

A property-bag catalog of concrete machines (German-speaking market OEMs) that fill the
Ausführungsart slots. Each machine carries operating cost / fuel / mob-demob (+ free
spec properties) in `eigenschaften`, and a productivity Leistungsprofil per Betriebsart.
The StateGraph selects a machine per slot and reads these into the calc; an unfilled
slot falls to Gate B (HITL). Numbers are realistic placeholders, not vendor data.

Exports MASCHINEN, maschinen_fuer(), validate().
"""

from decimal import Decimal, InvalidOperation

from shared.services.kalkulation_v2.ausfuehrungsarten import AUSFUEHRUNGSARTEN
from shared.services.kalkulation_v2.betriebsarten import BETRIEBSARTEN
from shared.services.kalkulation_v2.model import (
    D,
    Leistungsprofil,
    Maschine,
    MaschinenWert,
)


def _w(wert, einheit: str | None = None) -> MaschinenWert:
    """Wrap a property value. Numeric strings ('240', '1.00') become Decimal; genuine
    text ('Diesel') and bool (True) pass through unchanged."""
    if isinstance(wert, str):
        try:
            wert = D(wert)
        except InvalidOperation:
            pass
    return MaschinenWert(wert=wert, einheit=einheit)


def _p(betriebsart: str, leistung, einheit: str) -> Leistungsprofil:
    return Leistungsprofil(
        betriebsart_code=betriebsart, leistung=D(leistung), einheit=einheit
    )


def _m(
    code, hersteller, modell, aa, kosten, kraftstoff, mobil, demobil, profile, **extra
) -> Maschine:
    eig = {
        "betriebskosten_eur_pro_h": _w(kosten, "€/h"),
        "kraftstoff_l_pro_h": _w(kraftstoff, "l/h"),
        "mobilisierung_eur": _w(mobil, "€"),
        "demobilisierung_eur": _w(demobil, "€"),
    }
    eig.update({k: _w(v[0], v[1]) for k, v in extra.items()})
    return Maschine(
        code=code,
        hersteller=hersteller,
        modell=modell,
        ausfuehrungsart_code=aa,
        eigenschaften=eig,
        leistungsprofile=profile,
    )


_FLEET: list[Maschine] = [
    # --- Kaltfräsen (AA_KALTFRAESE): Regel-/Feinfräsen, m²/h ---
    _m(
        "WIRTGEN_W100CFI",
        "Wirtgen",
        "W 100 CFi",
        "AA_KALTFRAESE",
        "240",
        "55",
        "450",
        "450",
        [_p("regelfraesen", "520", "m2/h"), _p("feinfraesen", "240", "m2/h")],
        arbeitsbreite_m=("1.00", "m"),
        max_fraestiefe_mm=("330", "mm"),
        gnss_steuerung=(True, None),
    ),
    _m(
        "WIRTGEN_W150CFI",
        "Wirtgen",
        "W 150 CFi",
        "AA_KALTFRAESE",
        "310",
        "75",
        "600",
        "600",
        [_p("regelfraesen", "850", "m2/h"), _p("feinfraesen", "380", "m2/h")],
        arbeitsbreite_m=("1.50", "m"),
        gnss_steuerung=(True, None),
    ),
    _m(
        "CAT_PM312",
        "Caterpillar",
        "PM312",
        "AA_KALTFRAESE",
        "260",
        "60",
        "500",
        "500",
        [_p("regelfraesen", "560", "m2/h"), _p("feinfraesen", "260", "m2/h")],
        arbeitsbreite_m=("1.20", "m"),
    ),
    _m(
        "BOMAG_BM1200",
        "Bomag",
        "BM 1200/35",
        "AA_KALTFRAESE",
        "250",
        "58",
        "480",
        "480",
        [_p("regelfraesen", "540", "m2/h"), _p("feinfraesen", "250", "m2/h")],
        arbeitsbreite_m=("1.20", "m"),
    ),
    # --- Demarkierung (AA_MARKFRAESE): m/h, by material/method ---
    _m(
        "WIRTGEN_W35I",
        "Wirtgen",
        "W 35i",
        "AA_MARKFRAESE",
        "150",
        "18",
        "300",
        "300",
        [_p("demark_farbe", "300", "m/h"), _p("demark_plastik", "150", "m/h")],
        arbeitsbreite_m=("0.35", "m"),
        verfahren=("Fräsen", None),
    ),
    _m(
        "VONARX_FR200",
        "Von Arx",
        "FR 200",
        "AA_MARKFRAESE",
        "80",
        "8",
        "150",
        "150",
        [_p("demark_farbe", "220", "m/h"), _p("demark_plastik", "110", "m/h")],
        verfahren=("Fräsen", None),
    ),
    _m(
        "BLASTRAC_18DPS",
        "Blastrac",
        "1-8DPS75",
        "AA_MARKFRAESE",
        "95",
        "10",
        "180",
        "180",
        [_p("demark_farbe", "180", "m/h"), _p("demark_plastik", "140", "m/h")],
        verfahren=("Kugelstrahlen", None),
    ),
    _m(
        "HAMMELMANN_HDM",
        "Hammelmann",
        "HDP Demarkierung",
        "AA_MARKFRAESE",
        "320",
        "40",
        "500",
        "500",
        [_p("demark_hochdruck", "200", "m/h")],
        verfahren=("Hochdruckwasser", None),
    ),
    # --- Bagger (AA_BAGGER): Boden abtragen m³/h, Asphalt aufbrechen m²/h ---
    _m(
        "CAT_323",
        "Caterpillar",
        "323",
        "AA_BAGGER",
        "130",
        "19",
        "350",
        "350",
        [
            _p("boden_abtragen", "48", "m3/h"),
            Leistungsprofil(
                betriebsart_code="asphalt_aufbrechen",
                leistung=D("55"),
                einheit="m2/h",
                eigenschaften={"betriebskosten_eur_pro_h": _w("155", "€/h")},
            ),
        ],  # Aufbruchhammer-Verschleiß
        einsatzgewicht_t=("24", "t"),
    ),
    _m(
        "LIEBHERR_R926",
        "Liebherr",
        "R 926",
        "AA_BAGGER",
        "125",
        "18",
        "350",
        "350",
        [_p("boden_abtragen", "45", "m3/h"), _p("asphalt_aufbrechen", "52", "m2/h")],
    ),
    _m(
        "VOLVO_EC250",
        "Volvo CE",
        "EC250E",
        "AA_BAGGER",
        "128",
        "19",
        "350",
        "350",
        [_p("boden_abtragen", "47", "m3/h"), _p("asphalt_aufbrechen", "54", "m2/h")],
    ),
    _m(
        "KOMATSU_PC290",
        "Komatsu",
        "PC290",
        "AA_BAGGER",
        "132",
        "20",
        "360",
        "360",
        [_p("boden_abtragen", "49", "m3/h"), _p("asphalt_aufbrechen", "56", "m2/h")],
    ),
    # --- Fugenschneider (AA_SCHNEIDER): m/h, schneiden + Naht aufweiten ---
    _m(
        "LISSMAC_MC600",
        "Lissmac",
        "Multicut 600",
        "AA_SCHNEIDER",
        "45",
        "5",
        "120",
        "120",
        [_p("asphalt_schneiden", "80", "m/h"), _p("fuge_aufweiten", "60", "m/h")],
    ),
    _m(
        "CEDIMA_CF",
        "Cedima",
        "CF Serie",
        "AA_SCHNEIDER",
        "42",
        "4",
        "110",
        "110",
        [_p("asphalt_schneiden", "75", "m/h"), _p("fuge_aufweiten", "58", "m/h")],
    ),
    _m(
        "HUSQVARNA_FS7000",
        "Husqvarna",
        "FS 7000",
        "AA_SCHNEIDER",
        "48",
        "5",
        "120",
        "120",
        [_p("asphalt_schneiden", "82", "m/h"), _p("fuge_aufweiten", "62", "m/h")],
    ),
    # --- Radlader solo (AA_RADLADER): Schüttgut liefern/legen m³/h ---
    _m(
        "LIEBHERR_L538",
        "Liebherr",
        "L 538",
        "AA_RADLADER",
        "75",
        "14",
        "250",
        "250",
        [_p("schuettgut_einbau", "42", "m3/h")],
    ),
    _m(
        "VOLVO_L110H",
        "Volvo CE",
        "L110H",
        "AA_RADLADER",
        "78",
        "15",
        "250",
        "250",
        [_p("schuettgut_einbau", "44", "m3/h")],
    ),
    _m(
        "CAT_950GC",
        "Caterpillar",
        "950 GC",
        "AA_RADLADER",
        "72",
        "13",
        "250",
        "250",
        [_p("schuettgut_einbau", "40", "m3/h")],
    ),
    _m(
        "JOHNDEERE_624P",
        "John Deere",
        "624 P",
        "AA_RADLADER",
        "74",
        "14",
        "250",
        "250",
        [_p("schuettgut_einbau", "41", "m3/h")],
    ),
    # --- Grader solo (AA_GRADER_SOLO): Profilieren / Oberboden andecken m²/h ---
    _m(
        "CAT_140GC",
        "Caterpillar",
        "140 GC",
        "AA_GRADER_SOLO",
        "95",
        "14",
        "300",
        "300",
        [_p("profilieren", "500", "m2/h"), _p("oberboden_andecken", "420", "m2/h")],
    ),
    _m(
        "JOHNDEERE_620G",
        "John Deere",
        "620 G",
        "AA_GRADER_SOLO",
        "92",
        "14",
        "300",
        "300",
        [_p("profilieren", "480", "m2/h"), _p("oberboden_andecken", "400", "m2/h")],
    ),
    _m(
        "VOLVO_G930",
        "Volvo CE",
        "G930",
        "AA_GRADER_SOLO",
        "98",
        "15",
        "300",
        "300",
        [_p("profilieren", "510", "m2/h"), _p("oberboden_andecken", "430", "m2/h")],
    ),
    _m(
        "KOMATSU_GD555",
        "Komatsu",
        "GD555",
        "AA_GRADER_SOLO",
        "94",
        "14",
        "300",
        "300",
        [_p("profilieren", "490", "m2/h"), _p("oberboden_andecken", "410", "m2/h")],
    ),
    # --- Walze (AA_WALZE): flächig + je Übergang, m²/h ---
    _m(
        "HAMM_HD90",
        "Hamm",
        "HD+ 90",
        "AA_WALZE",
        "50",
        "9",
        "200",
        "200",
        [
            _p("verdichten_flaeche", "400", "m2/h"),
            _p("verdichten_uebergang", "1200", "m2/h"),
        ],
    ),
    _m(
        "BOMAG_BW174",
        "Bomag",
        "BW 174",
        "AA_WALZE",
        "52",
        "9",
        "200",
        "200",
        [
            _p("verdichten_flaeche", "410", "m2/h"),
            _p("verdichten_uebergang", "1250", "m2/h"),
        ],
    ),
    _m(
        "CAT_CB13",
        "Caterpillar",
        "CB13",
        "AA_WALZE",
        "51",
        "9",
        "200",
        "200",
        [
            _p("verdichten_flaeche", "405", "m2/h"),
            _p("verdichten_uebergang", "1220", "m2/h"),
        ],
    ),
    _m(
        "DYNAPAC_CA2500",
        "Dynapac",
        "CA2500",
        "AA_WALZE",
        "49",
        "9",
        "200",
        "200",
        [
            _p("verdichten_flaeche", "395", "m2/h"),
            _p("verdichten_uebergang", "1180", "m2/h"),
        ],
    ),
    _m(
        "AMMANN_ARX90",
        "Ammann",
        "ARX 90",
        "AA_WALZE",
        "50",
        "9",
        "200",
        "200",
        [
            _p("verdichten_flaeche", "400", "m2/h"),
            _p("verdichten_uebergang", "1200", "m2/h"),
        ],
    ),
    # --- kleine Tandemwalze Bankett (AA_BANKETTWALZE): m²/h ---
    _m(
        "HAMM_HD12",
        "Hamm",
        "HD 12",
        "AA_BANKETTWALZE",
        "45",
        "6",
        "150",
        "150",
        [_p("bankett_verdichten", "700", "m2/h")],
    ),
    _m(
        "BOMAG_BW100",
        "Bomag",
        "BW 100 AD",
        "AA_BANKETTWALZE",
        "44",
        "6",
        "150",
        "150",
        [_p("bankett_verdichten", "690", "m2/h")],
    ),
    _m(
        "WACKER_RD16",
        "Wacker Neuson",
        "RD16",
        "AA_BANKETTWALZE",
        "42",
        "5",
        "140",
        "140",
        [_p("bankett_verdichten", "650", "m2/h")],
    ),
    _m(
        "AMMANN_AV70",
        "Ammann",
        "AV 70",
        "AA_BANKETTWALZE",
        "45",
        "6",
        "150",
        "150",
        [_p("bankett_verdichten", "700", "m2/h")],
    ),
    # --- Fertiger FSS (AA_FERTIGER): liefern/legen/abziehen m²/h ---
    _m(
        "VOEGELE_S1800_FSS",
        "Vögele",
        "Super 1800-3i",
        "AA_FERTIGER",
        "180",
        "25",
        "600",
        "600",
        [_p("schuettgut_einbau", "600", "m2/h")],
    ),
    _m(
        "DYNAPAC_SD2500_FSS",
        "Dynapac",
        "SD2500CS",
        "AA_FERTIGER",
        "175",
        "24",
        "600",
        "600",
        [_p("schuettgut_einbau", "580", "m2/h")],
    ),
    # --- Asphalt-Einbauzug (AA_ASPHALT_FERTIGER): composite, t/h, Kraftstoff im Satz
    # ---
    _m(
        "VOEGELE_EINBAUZUG",
        "Vögele",
        "Super 1800-3i + MT 3000-3i + Hamm",
        "AA_ASPHALT_FERTIGER",
        "520",
        "0",
        "1200",
        "1200",
        [_p("asphalt_einbau", "90", "t/h")],
        zusammenstellung=("Fertiger + Beschicker + 2 Walzen", None),
    ),
    _m(
        "CAT_EINBAUZUG",
        "Caterpillar",
        "AP500F + BB + 2 Walzen",
        "AA_ASPHALT_FERTIGER",
        "500",
        "0",
        "1100",
        "1100",
        [_p("asphalt_einbau", "85", "t/h")],
        zusammenstellung=("Fertiger + Beschicker + 2 Walzen", None),
    ),
    # --- Bankettfertiger (AA_BANKETT_FERTIGER): m²/h ---
    _m(
        "VOEGELE_S700",
        "Vögele",
        "Super 700",
        "AA_BANKETT_FERTIGER",
        "120",
        "14",
        "350",
        "350",
        [_p("bankett_einbau", "350", "m2/h")],
    ),
    # --- Kehrmaschine (AA_KEHRMASCHINE): m²/h ---
    _m(
        "BUCHER_V65",
        "Bucher",
        "V65",
        "AA_KEHRMASCHINE",
        "60",
        "8",
        "200",
        "200",
        [_p("kehren", "1200", "m2/h")],
    ),
    _m(
        "AEBI_SWINGO",
        "Aebi Schmidt",
        "Swingo",
        "AA_KEHRMASCHINE",
        "62",
        "8",
        "200",
        "200",
        [_p("kehren", "1250", "m2/h")],
    ),
    _m(
        "FAUN_VIAJET6",
        "Faun",
        "Viajet 6",
        "AA_KEHRMASCHINE",
        "65",
        "9",
        "200",
        "200",
        [_p("kehren", "1300", "m2/h")],
    ),
    # --- HD-Wasch-Sauganlage (AA_HD_WASCHSAUG): m²/h ---
    _m(
        "HAMMELMANN_WS",
        "Hammelmann",
        "Wasch-Saug-Einheit",
        "AA_HD_WASCHSAUG",
        "320",
        "40",
        "500",
        "500",
        [_p("hochdruckreinigen", "1500", "m2/h")],
    ),
    _m(
        "FALCH_WS",
        "Falch",
        "Wasch-Saug-Einheit",
        "AA_HD_WASCHSAUG",
        "310",
        "38",
        "500",
        "500",
        [_p("hochdruckreinigen", "1450", "m2/h")],
    ),
    # --- Rampenspritzgerät (AA_SPRITZGERAET): m²/h ---
    _m(
        "STRASSMAYR_S31",
        "Strassmayr",
        "S31",
        "AA_SPRITZGERAET",
        "90",
        "10",
        "250",
        "250",
        [_p("anspritzen", "4000", "m2/h")],
    ),
    _m(
        "SECMAIR_CHIP",
        "Secmair",
        "Chipsealer",
        "AA_SPRITZGERAET",
        "95",
        "11",
        "260",
        "260",
        [_p("anspritzen", "4200", "m2/h")],
    ),
    _m(
        "BREINING_SPRAY",
        "Breining",
        "Spray",
        "AA_SPRITZGERAET",
        "88",
        "10",
        "250",
        "250",
        [_p("anspritzen", "3900", "m2/h")],
    ),
    # --- Splittstreuer (AA_ABSTREUER): m²/h ---
    _m(
        "STREUMASTER_SW5",
        "Streumaster",
        "SW 5 MC",
        "AA_ABSTREUER",
        "75",
        "9",
        "250",
        "250",
        [_p("abstreuen", "3000", "m2/h")],
    ),
    _m(
        "KIRCHHOFF_STR",
        "Kirchhoff",
        "Streuer",
        "AA_ABSTREUER",
        "72",
        "9",
        "240",
        "240",
        [_p("abstreuen", "2900", "m2/h")],
    ),
    # --- Fugenvergussgerät (AA_FUGENGERAET): Fugenverguss + Randabdichtung, m/h ---
    _m(
        "FUGENKOCHER_STD",
        "Generic",
        "Fugenkocher/-vergussgerät",
        "AA_FUGENGERAET",
        "30",
        "3",
        "120",
        "120",
        [_p("fugenverguss", "80", "m/h"), _p("randabdichtung", "60", "m/h")],
    ),
    _m(
        "CRAFCO_EZ",
        "Crafco",
        "EZ Pour",
        "AA_FUGENGERAET",
        "32",
        "3",
        "120",
        "120",
        [_p("fugenverguss", "85", "m/h"), _p("randabdichtung", "62", "m/h")],
    ),
    # --- DSK-/Slurry-Einbaumaschine (AA_DSK): m²/h ---
    _m(
        "BREINING_DSK",
        "Breining",
        "DSK-/Slurry-Fertiger",
        "AA_DSK",
        "180",
        "20",
        "450",
        "450",
        [_p("dsk_einbau", "2000", "m2/h")],
    ),
    _m(
        "STREUMASTER_DSK",
        "Streumaster",
        "Slurry-Fertiger",
        "AA_DSK",
        "175",
        "19",
        "440",
        "440",
        [_p("dsk_einbau", "1900", "m2/h")],
    ),
    # --- Gussasphalt-Fertiger/Kocher (AA_GUSSASPHALT): m²/h ---
    _m(
        "LINNHOFF_GUSS",
        "Linnhoff",
        "Gussasphaltfertiger",
        "AA_GUSSASPHALT",
        "160",
        "16",
        "400",
        "400",
        [_p("gussasphalt_einbau", "85", "m2/h")],
    ),
    _m(
        "GMEINDER_GUSS",
        "Gmeinder",
        "Kocher + Bohle",
        "AA_GUSSASPHALT",
        "150",
        "15",
        "380",
        "380",
        [_p("gussasphalt_einbau", "75", "m2/h")],
    ),
    # --- Composite sets (existing lumped rates): Radlader+Walze, Grader+Walze ---
    _m(
        "LIEBHERR_EINBAU_SET",
        "Liebherr",
        "L 538 + Walze (Set)",
        "AA_RADLADER_WALZE",
        "120",
        "23",
        "400",
        "400",
        [_p("schuettgut_einbau", "35", "m3/h")],
        zusammenstellung=("Radlader + Walze", None),
    ),
    _m(
        "CAT_PLANUM_SET",
        "Caterpillar",
        "140 GC + Walze (Set)",
        "AA_GRADER",
        "145",
        "23",
        "400",
        "400",
        [_p("planum_herstellen", "250", "m2/h")],
        zusammenstellung=("Grader + Walze", None),
    ),
]

MASCHINEN: dict[str, Maschine] = {m.code: m for m in _FLEET}


def maschinen_fuer(ausfuehrungsart_code: str) -> list[Maschine]:
    """Candidate machines for an Ausführungsart slot (for the Gate A picker /
    auto-select)."""
    return [
        m for m in MASCHINEN.values() if m.ausfuehrungsart_code == ausfuehrungsart_code
    ]


def maschinen_sortiert(
    ausfuehrungsart_code: str,
    *,
    betriebsart_code: str | None = None,
    bedarf_pro_stunde: Decimal | None = None,
) -> list[Maschine]:
    """Candidates right-sized to the job: the smallest machine whose capacity
    (productivity for `betriebsart_code`) still clears `bedarf_pro_stunde` comes first,
    then larger ones, then any too small (largest of those first), then any without a
    profile for the Betriebsart. So `[0]` is the principled default — smallest
    sufficient, or the biggest available if none suffices. Without a Betriebsart/demand
    it falls back to fleet order (no right-sizing)."""
    kandidaten = maschinen_fuer(ausfuehrungsart_code)
    if betriebsart_code is None or bedarf_pro_stunde is None:
        return kandidaten

    def kapazitaet(m: Maschine) -> Decimal | None:
        profil = m.leistung_fuer(betriebsart_code)
        return profil.leistung if profil is not None else None

    mit = [(m, k) for m in kandidaten if (k := kapazitaet(m)) is not None]
    ohne = [m for m in kandidaten if kapazitaet(m) is None]
    genug = sorted(
        (m for m, k in mit if k >= bedarf_pro_stunde), key=lambda m: kapazitaet(m)
    )
    zu_klein = sorted(
        (m for m, k in mit if k < bedarf_pro_stunde),
        key=lambda m: kapazitaet(m),
        reverse=True,
    )
    return [*genug, *zu_klein, *ohne]


def validate() -> list[str]:
    fehler: list[str] = []
    aa_codes = {a.code for a in AUSFUEHRUNGSARTEN.values()}
    if len(MASCHINEN) != len(_FLEET):
        fehler.append("doppelter Maschinen-Code im Fleet")
    for m in MASCHINEN.values():
        if m.ausfuehrungsart_code not in aa_codes:
            fehler.append(
                f"Maschine '{m.code}' -> unbekannte Ausführungsart "
                f"'{m.ausfuehrungsart_code}'"
            )
        for p in m.leistungsprofile:
            if p.betriebsart_code not in BETRIEBSARTEN:
                fehler.append(
                    f"Maschine '{m.code}' -> unbekannte Betriebsart "
                    f"'{p.betriebsart_code}'"
                )
    return fehler


_fehler = validate()
if _fehler:
    raise ValueError("Ungültiger Maschinen-Katalog:\n  " + "\n  ".join(_fehler))


if __name__ == "__main__":
    by_slot: dict[str, list[str]] = {}
    for m in MASCHINEN.values():
        by_slot.setdefault(m.ausfuehrungsart_code, []).append(
            f"{m.hersteller} {m.modell}"
        )
    print(f"{len(MASCHINEN)} Maschinen über {len(by_slot)} Ausführungsart-Slots:")
    for slot, names in sorted(by_slot.items()):
        print(f"  {slot:24} {len(names)}x  {', '.join(names)}")
