"""
lieferanten_preise.py — STATIC price list (no RNG at runtime).

PREISE is the flat join table (lieferant_code, baustoff_code, preis_eur_pro_t).
Hand-edit freely. lade_preise() attaches these to the supplier objects,
resolving baustoff codes to ids against the current material catalog.
"""

from datetime import date

from shared.services.kalkulation_v2.model import BaustoffPreis, D

# (lieferant_code, baustoff_code, preis_eur_pro_t)
PREISE: list[tuple[str, str, str]] = [
    # LIEF_001 — Harzland Schotter & Splitt GmbH (99734 Nordhausen)
    ("LIEF_001", "FSS_0_32", "15.60"),
    ("LIEF_001", "FSS_0_45", "13.90"),
    ("LIEF_001", "STS_0_32", "19.90"),
    ("LIEF_001", "STS_0_45", "15.80"),
    ("LIEF_001", "SCHOTTER_0_56", "14.60"),
    ("LIEF_001", "MG_B2_0_32", "18.80"),
    ("LIEF_001", "SPLITT_2_5", "21.50"),
    ("LIEF_001", "SPLITT_5_8", "23.70"),
    ("LIEF_001", "SPLITT_8_11", "19.60"),
    ("LIEF_001", "SPLITT_11_16", "21.20"),

    # LIEF_002 — Kyffhäuser Naturstein GmbH (99706 Sondershausen)
    ("LIEF_002", "FSS_0_32", "14.40"),
    ("LIEF_002", "FSS_0_45", "13.60"),
    ("LIEF_002", "STS_0_32", "18.60"),
    ("LIEF_002", "STS_0_45", "19.70"),
    ("LIEF_002", "SCHOTTER_0_56", "12.80"),
    ("LIEF_002", "MG_B2_0_32", "18.00"),
    ("LIEF_002", "SPLITT_2_5", "25.60"),
    ("LIEF_002", "SPLITT_5_8", "26.80"),
    ("LIEF_002", "SPLITT_8_11", "23.20"),
    ("LIEF_002", "SPLITT_11_16", "21.00"),

    # LIEF_003 — Unstrut Kies & Sand GmbH (99974 Mühlhausen)
    ("LIEF_003", "FSS_0_32", "18.80"),
    ("LIEF_003", "FSS_0_45", "13.40"),
    ("LIEF_003", "STS_0_32", "21.00"),
    ("LIEF_003", "STS_0_45", "16.90"),
    ("LIEF_003", "SCHOTTER_0_56", "12.90"),
    ("LIEF_003", "MG_B2_0_32", "17.40"),
    ("LIEF_003", "KIES_2_8", "16.50"),
    ("LIEF_003", "KIES_8_16", "18.00"),
    ("LIEF_003", "KIES_16_32", "14.00"),
    ("LIEF_003", "SAND_0_2", "13.70"),
    ("LIEF_003", "BRECHSAND_0_2", "16.10"),

    # LIEF_004 — Thüringer Mineralgemisch GmbH (99610 Sömmerda)
    ("LIEF_004", "FSS_0_32", "15.90"),
    ("LIEF_004", "FSS_0_45", "15.70"),
    ("LIEF_004", "STS_0_32", "16.60"),
    ("LIEF_004", "STS_0_45", "15.70"),
    ("LIEF_004", "SCHOTTER_0_56", "13.20"),
    ("LIEF_004", "MG_B2_0_32", "20.60"),
    ("LIEF_004", "KIES_2_8", "17.10"),
    ("LIEF_004", "KIES_8_16", "15.60"),
    ("LIEF_004", "KIES_16_32", "15.80"),
    ("LIEF_004", "SAND_0_2", "13.20"),
    ("LIEF_004", "BRECHSAND_0_2", "14.50"),
    ("LIEF_004", "OBERBODEN", "7.80"),
    ("LIEF_004", "GROBK_BODEN", "10.90"),

    # LIEF_005 — Mitteldeutsche Baustoffe AG (99086 Erfurt)
    ("LIEF_005", "FSS_0_32", "15.30"),
    ("LIEF_005", "FSS_0_45", "15.80"),
    ("LIEF_005", "STS_0_32", "19.20"),
    ("LIEF_005", "STS_0_45", "20.00"),
    ("LIEF_005", "SCHOTTER_0_56", "15.40"),
    ("LIEF_005", "MG_B2_0_32", "18.40"),
    ("LIEF_005", "KIES_2_8", "20.00"),
    ("LIEF_005", "KIES_8_16", "14.60"),
    ("LIEF_005", "KIES_16_32", "15.10"),
    ("LIEF_005", "SAND_0_2", "14.40"),
    ("LIEF_005", "BRECHSAND_0_2", "13.90"),
    ("LIEF_005", "OBERBODEN", "7.20"),
    ("LIEF_005", "GROBK_BODEN", "8.90"),

    # LIEF_006 — Gothaer Hartsteinwerk GmbH (99867 Gotha)
    ("LIEF_006", "FSS_0_32", "17.30"),
    ("LIEF_006", "FSS_0_45", "16.60"),
    ("LIEF_006", "STS_0_32", "19.50"),
    ("LIEF_006", "STS_0_45", "20.00"),
    ("LIEF_006", "SCHOTTER_0_56", "13.60"),
    ("LIEF_006", "MG_B2_0_32", "20.70"),
    ("LIEF_006", "SPLITT_2_5", "25.40"),
    ("LIEF_006", "SPLITT_5_8", "24.20"),
    ("LIEF_006", "SPLITT_8_11", "22.40"),
    ("LIEF_006", "SPLITT_11_16", "23.80"),

    # LIEF_007 — Wartburg Asphaltmischwerk GmbH (99817 Eisenach)
    ("LIEF_007", "ASPHALT_AC32TS", "84.00"),
    ("LIEF_007", "ASPHALT_AC16BS", "84.00"),
    ("LIEF_007", "ASPHALT_AC11DS", "99.50"),
    ("LIEF_007", "SMA_8_S", "97.00"),
    ("LIEF_007", "BITUMEN_50_70", "632.00"),
    ("LIEF_007", "PMB_45_80", "913.00"),

    # LIEF_008 — Salza Kieswerk GmbH (99947 Bad Langensalza)
    ("LIEF_008", "FSS_0_32", "18.80"),
    ("LIEF_008", "FSS_0_45", "16.90"),
    ("LIEF_008", "STS_0_32", "17.90"),
    ("LIEF_008", "STS_0_45", "17.40"),
    ("LIEF_008", "SCHOTTER_0_56", "15.10"),
    ("LIEF_008", "MG_B2_0_32", "16.80"),
    ("LIEF_008", "KIES_2_8", "17.30"),
    ("LIEF_008", "KIES_8_16", "14.90"),
    ("LIEF_008", "KIES_16_32", "13.70"),
    ("LIEF_008", "SAND_0_2", "11.70"),
    ("LIEF_008", "BRECHSAND_0_2", "16.70"),

    # LIEF_009 — Eichsfeld Naturstein GmbH (37308 Heilbad Heiligenstadt)
    ("LIEF_009", "FSS_0_32", "14.70"),
    ("LIEF_009", "FSS_0_45", "14.30"),
    ("LIEF_009", "STS_0_32", "18.40"),
    ("LIEF_009", "STS_0_45", "20.00"),
    ("LIEF_009", "SCHOTTER_0_56", "12.70"),
    ("LIEF_009", "MG_B2_0_32", "19.30"),
    ("LIEF_009", "SPLITT_2_5", "25.10"),
    ("LIEF_009", "SPLITT_5_8", "26.30"),
    ("LIEF_009", "SPLITT_8_11", "24.80"),
    ("LIEF_009", "SPLITT_11_16", "23.90"),

    # LIEF_010 — Arnstädter Schotterwerk GmbH (99310 Arnstadt)
    ("LIEF_010", "FSS_0_32", "15.40"),
    ("LIEF_010", "FSS_0_45", "15.10"),
    ("LIEF_010", "STS_0_32", "18.30"),
    ("LIEF_010", "STS_0_45", "20.00"),
    ("LIEF_010", "SCHOTTER_0_56", "16.30"),
    ("LIEF_010", "MG_B2_0_32", "17.60"),
    ("LIEF_010", "SPLITT_2_5", "22.40"),
    ("LIEF_010", "SPLITT_5_8", "21.80"),
    ("LIEF_010", "SPLITT_8_11", "20.90"),
    ("LIEF_010", "SPLITT_11_16", "21.50"),

    # LIEF_011 — Ilm-Kies GmbH (98693 Ilmenau)
    ("LIEF_011", "FSS_0_32", "16.90"),
    ("LIEF_011", "FSS_0_45", "14.40"),
    ("LIEF_011", "STS_0_32", "16.30"),
    ("LIEF_011", "STS_0_45", "17.60"),
    ("LIEF_011", "SCHOTTER_0_56", "13.90"),
    ("LIEF_011", "MG_B2_0_32", "19.90"),
    ("LIEF_011", "KIES_2_8", "19.80"),
    ("LIEF_011", "KIES_8_16", "17.40"),
    ("LIEF_011", "KIES_16_32", "15.50"),
    ("LIEF_011", "SAND_0_2", "13.80"),
    ("LIEF_011", "BRECHSAND_0_2", "16.20"),

    # LIEF_012 — Rennsteig Hartstein GmbH (98527 Suhl)
    ("LIEF_012", "FSS_0_32", "14.30"),
    ("LIEF_012", "FSS_0_45", "17.20"),
    ("LIEF_012", "STS_0_32", "20.60"),
    ("LIEF_012", "STS_0_45", "20.00"),
    ("LIEF_012", "SCHOTTER_0_56", "15.70"),
    ("LIEF_012", "MG_B2_0_32", "19.00"),
    ("LIEF_012", "SPLITT_2_5", "24.00"),
    ("LIEF_012", "SPLITT_5_8", "21.00"),
    ("LIEF_012", "SPLITT_8_11", "23.50"),
    ("LIEF_012", "SPLITT_11_16", "18.90"),

    # LIEF_013 — Südthüringer Baustoff-Recycling GmbH (98617 Meiningen)
    ("LIEF_013", "FSS_0_32", "14.40"),
    ("LIEF_013", "FSS_0_45", "14.10"),
    ("LIEF_013", "STS_0_32", "17.20"),
    ("LIEF_013", "STS_0_45", "17.20"),
    ("LIEF_013", "SCHOTTER_0_56", "12.50"),
    ("LIEF_013", "MG_B2_0_32", "16.70"),
    ("LIEF_013", "RC_SCHOTTER_0_45", "8.30"),
    ("LIEF_013", "RC_0_32", "7.30"),
    ("LIEF_013", "OBERBODEN", "6.90"),
    ("LIEF_013", "GROBK_BODEN", "8.90"),

    # LIEF_014 — Saale Splitt & Schotter GmbH (07318 Saalfeld)
    ("LIEF_014", "FSS_0_32", "18.30"),
    ("LIEF_014", "FSS_0_45", "16.00"),
    ("LIEF_014", "STS_0_32", "17.10"),
    ("LIEF_014", "STS_0_45", "16.70"),
    ("LIEF_014", "SCHOTTER_0_56", "13.80"),
    ("LIEF_014", "MG_B2_0_32", "18.80"),
    ("LIEF_014", "SPLITT_2_5", "22.00"),
    ("LIEF_014", "SPLITT_5_8", "26.10"),
    ("LIEF_014", "SPLITT_8_11", "25.90"),
    ("LIEF_014", "SPLITT_11_16", "21.40"),

    # LIEF_015 — Schwarzatal Naturstein GmbH (07407 Rudolstadt)
    ("LIEF_015", "FSS_0_32", "16.40"),
    ("LIEF_015", "FSS_0_45", "13.60"),
    ("LIEF_015", "STS_0_32", "16.80"),
    ("LIEF_015", "STS_0_45", "17.20"),
    ("LIEF_015", "SCHOTTER_0_56", "13.40"),
    ("LIEF_015", "MG_B2_0_32", "21.40"),
    ("LIEF_015", "SPLITT_2_5", "22.30"),
    ("LIEF_015", "SPLITT_5_8", "20.40"),
    ("LIEF_015", "SPLITT_8_11", "25.60"),
    ("LIEF_015", "SPLITT_11_16", "21.80"),

    # LIEF_016 — Saaletal Asphalt GmbH (07745 Jena)
    ("LIEF_016", "ASPHALT_AC32TS", "66.50"),
    ("LIEF_016", "ASPHALT_AC16BS", "85.50"),
    ("LIEF_016", "ASPHALT_AC11DS", "81.50"),
    ("LIEF_016", "SMA_8_S", "112.00"),
    ("LIEF_016", "BITUMEN_50_70", "681.00"),
    ("LIEF_016", "PMB_45_80", "968.00"),

    # LIEF_017 — Elstertal Kies & Beton GmbH (07545 Gera)
    ("LIEF_017", "FSS_0_32", "17.40"),
    ("LIEF_017", "FSS_0_45", "14.40"),
    ("LIEF_017", "STS_0_32", "18.30"),
    ("LIEF_017", "STS_0_45", "16.30"),
    ("LIEF_017", "SCHOTTER_0_56", "15.60"),
    ("LIEF_017", "MG_B2_0_32", "19.80"),
    ("LIEF_017", "KIES_2_8", "18.90"),
    ("LIEF_017", "KIES_8_16", "15.70"),
    ("LIEF_017", "KIES_16_32", "14.20"),
    ("LIEF_017", "SAND_0_2", "14.60"),
    ("LIEF_017", "BRECHSAND_0_2", "17.60"),

    # LIEF_018 — Frankenwald-Grenze Schotter GmbH (96515 Sonneberg)
    ("LIEF_018", "FSS_0_32", "18.20"),
    ("LIEF_018", "FSS_0_45", "16.80"),
    ("LIEF_018", "STS_0_32", "20.80"),
    ("LIEF_018", "STS_0_45", "19.30"),
    ("LIEF_018", "SCHOTTER_0_56", "13.30"),
    ("LIEF_018", "MG_B2_0_32", "19.70"),
    ("LIEF_018", "SPLITT_2_5", "23.70"),
    ("LIEF_018", "SPLITT_5_8", "20.40"),
    ("LIEF_018", "SPLITT_8_11", "19.50"),
    ("LIEF_018", "SPLITT_11_16", "20.20"),

    # LIEF_019 — Goldene Aue Kieswerk GmbH (06526 Sangerhausen)
    ("LIEF_019", "FSS_0_32", "15.30"),
    ("LIEF_019", "FSS_0_45", "16.30"),
    ("LIEF_019", "STS_0_32", "21.60"),
    ("LIEF_019", "STS_0_45", "17.70"),
    ("LIEF_019", "SCHOTTER_0_56", "16.30"),
    ("LIEF_019", "MG_B2_0_32", "22.40"),
    ("LIEF_019", "KIES_2_8", "19.80"),
    ("LIEF_019", "KIES_8_16", "15.80"),
    ("LIEF_019", "KIES_16_32", "14.20"),
    ("LIEF_019", "SAND_0_2", "12.30"),
    ("LIEF_019", "BRECHSAND_0_2", "14.10"),

    # LIEF_020 — Mansfelder Hartstein GmbH (06295 Lutherstadt Eisleben)
    ("LIEF_020", "FSS_0_32", "15.10"),
    ("LIEF_020", "FSS_0_45", "16.00"),
    ("LIEF_020", "STS_0_32", "21.30"),
    ("LIEF_020", "STS_0_45", "19.80"),
    ("LIEF_020", "SCHOTTER_0_56", "14.30"),
    ("LIEF_020", "MG_B2_0_32", "20.40"),
    ("LIEF_020", "SPLITT_2_5", "26.90"),
    ("LIEF_020", "SPLITT_5_8", "20.80"),
    ("LIEF_020", "SPLITT_8_11", "23.70"),
    ("LIEF_020", "SPLITT_11_16", "24.20"),

    # LIEF_021 — Harzvorland Naturstein GmbH (06484 Quedlinburg)
    ("LIEF_021", "FSS_0_32", "17.80"),
    ("LIEF_021", "FSS_0_45", "16.60"),
    ("LIEF_021", "STS_0_32", "18.90"),
    ("LIEF_021", "STS_0_45", "16.30"),
    ("LIEF_021", "SCHOTTER_0_56", "15.60"),
    ("LIEF_021", "MG_B2_0_32", "18.60"),
    ("LIEF_021", "SPLITT_2_5", "26.90"),
    ("LIEF_021", "SPLITT_5_8", "26.90"),
    ("LIEF_021", "SPLITT_8_11", "22.00"),
    ("LIEF_021", "SPLITT_11_16", "21.00"),

    # LIEF_022 — Halberstädter Schotterwerk GmbH (38820 Halberstadt)
    ("LIEF_022", "FSS_0_32", "18.60"),
    ("LIEF_022", "FSS_0_45", "16.50"),
    ("LIEF_022", "STS_0_32", "17.20"),
    ("LIEF_022", "STS_0_45", "16.10"),
    ("LIEF_022", "SCHOTTER_0_56", "13.00"),
    ("LIEF_022", "MG_B2_0_32", "21.90"),
    ("LIEF_022", "SPLITT_2_5", "26.90"),
    ("LIEF_022", "SPLITT_5_8", "21.20"),
    ("LIEF_022", "SPLITT_8_11", "24.80"),
    ("LIEF_022", "SPLITT_11_16", "24.70"),

    # LIEF_023 — Brocken Diabas GmbH (38855 Wernigerode)
    ("LIEF_023", "FSS_0_32", "17.20"),
    ("LIEF_023", "FSS_0_45", "14.80"),
    ("LIEF_023", "STS_0_32", "19.30"),
    ("LIEF_023", "STS_0_45", "16.10"),
    ("LIEF_023", "SCHOTTER_0_56", "12.40"),
    ("LIEF_023", "MG_B2_0_32", "22.30"),
    ("LIEF_023", "SPLITT_2_5", "25.80"),
    ("LIEF_023", "SPLITT_5_8", "23.90"),
    ("LIEF_023", "SPLITT_8_11", "25.50"),
    ("LIEF_023", "SPLITT_11_16", "21.20"),

    # LIEF_024 — Bodetal Hartstein GmbH (06502 Thale)
    ("LIEF_024", "FSS_0_32", "18.30"),
    ("LIEF_024", "FSS_0_45", "16.90"),
    ("LIEF_024", "STS_0_32", "17.50"),
    ("LIEF_024", "STS_0_45", "16.70"),
    ("LIEF_024", "SCHOTTER_0_56", "13.60"),
    ("LIEF_024", "MG_B2_0_32", "18.10"),
    ("LIEF_024", "SPLITT_2_5", "25.30"),
    ("LIEF_024", "SPLITT_5_8", "22.00"),
    ("LIEF_024", "SPLITT_8_11", "22.10"),
    ("LIEF_024", "SPLITT_11_16", "19.30"),

    # LIEF_025 — Aschersleben Baustoffe GmbH (06449 Aschersleben)
    ("LIEF_025", "FSS_0_32", "18.40"),
    ("LIEF_025", "FSS_0_45", "14.80"),
    ("LIEF_025", "STS_0_32", "18.80"),
    ("LIEF_025", "STS_0_45", "18.50"),
    ("LIEF_025", "SCHOTTER_0_56", "16.10"),
    ("LIEF_025", "MG_B2_0_32", "19.10"),
    ("LIEF_025", "KIES_2_8", "19.60"),
    ("LIEF_025", "KIES_8_16", "16.50"),
    ("LIEF_025", "KIES_16_32", "15.60"),
    ("LIEF_025", "SAND_0_2", "13.50"),
    ("LIEF_025", "BRECHSAND_0_2", "13.30"),
    ("LIEF_025", "OBERBODEN", "7.10"),
    ("LIEF_025", "GROBK_BODEN", "9.30"),

    # LIEF_026 — Bode Kies & Sand GmbH (39418 Staßfurt)
    ("LIEF_026", "FSS_0_32", "14.10"),
    ("LIEF_026", "FSS_0_45", "16.80"),
    ("LIEF_026", "STS_0_32", "17.20"),
    ("LIEF_026", "STS_0_45", "17.90"),
    ("LIEF_026", "SCHOTTER_0_56", "15.40"),
    ("LIEF_026", "MG_B2_0_32", "19.90"),
    ("LIEF_026", "KIES_2_8", "16.60"),
    ("LIEF_026", "KIES_8_16", "16.60"),
    ("LIEF_026", "KIES_16_32", "15.70"),
    ("LIEF_026", "SAND_0_2", "14.50"),
    ("LIEF_026", "BRECHSAND_0_2", "13.70"),

    # LIEF_027 — Saale-Elbe Mineralstoffe GmbH (06406 Bernburg)
    ("LIEF_027", "FSS_0_32", "16.80"),
    ("LIEF_027", "FSS_0_45", "14.30"),
    ("LIEF_027", "STS_0_32", "17.80"),
    ("LIEF_027", "STS_0_45", "19.50"),
    ("LIEF_027", "SCHOTTER_0_56", "14.50"),
    ("LIEF_027", "MG_B2_0_32", "19.90"),

    # LIEF_028 — Saalekreis Asphaltmischwerk GmbH (06112 Halle (Saale))
    ("LIEF_028", "ASPHALT_AC32TS", "80.00"),
    ("LIEF_028", "ASPHALT_AC16BS", "94.50"),
    ("LIEF_028", "ASPHALT_AC11DS", "93.00"),
    ("LIEF_028", "SMA_8_S", "115.00"),
    ("LIEF_028", "BITUMEN_50_70", "598.00"),
    ("LIEF_028", "PMB_45_80", "879.00"),

    # LIEF_029 — Saale-Unstrut Schotter GmbH (06618 Naumburg)
    ("LIEF_029", "FSS_0_32", "17.40"),
    ("LIEF_029", "FSS_0_45", "15.20"),
    ("LIEF_029", "STS_0_32", "19.20"),
    ("LIEF_029", "STS_0_45", "17.90"),
    ("LIEF_029", "SCHOTTER_0_56", "16.30"),
    ("LIEF_029", "MG_B2_0_32", "20.70"),
    ("LIEF_029", "SPLITT_2_5", "27.40"),
    ("LIEF_029", "SPLITT_5_8", "26.70"),
    ("LIEF_029", "SPLITT_8_11", "21.10"),
    ("LIEF_029", "SPLITT_11_16", "22.00"),

    # LIEF_030 — Weißenfelser Kieswerk GmbH (06667 Weißenfels)
    ("LIEF_030", "FSS_0_32", "18.60"),
    ("LIEF_030", "FSS_0_45", "17.00"),
    ("LIEF_030", "STS_0_32", "17.00"),
    ("LIEF_030", "STS_0_45", "16.00"),
    ("LIEF_030", "SCHOTTER_0_56", "14.20"),
    ("LIEF_030", "MG_B2_0_32", "17.10"),
    ("LIEF_030", "KIES_2_8", "16.20"),
    ("LIEF_030", "KIES_8_16", "14.40"),
    ("LIEF_030", "KIES_16_32", "16.20"),
    ("LIEF_030", "SAND_0_2", "14.50"),
    ("LIEF_030", "BRECHSAND_0_2", "17.20"),

    # LIEF_031 — Elbe Baustoff-Recycling GmbH (39104 Magdeburg)
    ("LIEF_031", "FSS_0_32", "14.80"),
    ("LIEF_031", "FSS_0_45", "16.40"),
    ("LIEF_031", "STS_0_32", "19.90"),
    ("LIEF_031", "STS_0_45", "16.20"),
    ("LIEF_031", "SCHOTTER_0_56", "16.00"),
    ("LIEF_031", "MG_B2_0_32", "22.20"),
    ("LIEF_031", "RC_SCHOTTER_0_45", "8.50"),
    ("LIEF_031", "RC_0_32", "9.30"),
    ("LIEF_031", "OBERBODEN", "7.00"),
    ("LIEF_031", "GROBK_BODEN", "10.30"),

    # LIEF_032 — Coburger Land Schotter GmbH (96450 Coburg)
    ("LIEF_032", "FSS_0_32", "18.80"),
    ("LIEF_032", "FSS_0_45", "16.90"),
    ("LIEF_032", "STS_0_32", "17.20"),
    ("LIEF_032", "STS_0_45", "17.70"),
    ("LIEF_032", "SCHOTTER_0_56", "14.50"),
    ("LIEF_032", "MG_B2_0_32", "18.70"),
    ("LIEF_032", "SPLITT_2_5", "22.50"),
    ("LIEF_032", "SPLITT_5_8", "22.40"),
    ("LIEF_032", "SPLITT_8_11", "24.10"),
    ("LIEF_032", "SPLITT_11_16", "18.60"),

    # LIEF_033 — Frankenwald Diabaswerk GmbH (96317 Kronach)
    ("LIEF_033", "FSS_0_32", "16.70"),
    ("LIEF_033", "FSS_0_45", "15.20"),
    ("LIEF_033", "STS_0_32", "16.40"),
    ("LIEF_033", "STS_0_45", "17.10"),
    ("LIEF_033", "SCHOTTER_0_56", "14.90"),
    ("LIEF_033", "MG_B2_0_32", "19.60"),
    ("LIEF_033", "SPLITT_2_5", "21.60"),
    ("LIEF_033", "SPLITT_5_8", "27.00"),
    ("LIEF_033", "SPLITT_8_11", "24.60"),
    ("LIEF_033", "SPLITT_11_16", "24.60"),

    # LIEF_034 — Weißmain Kies & Sand GmbH (95326 Kulmbach)
    ("LIEF_034", "FSS_0_32", "14.60"),
    ("LIEF_034", "FSS_0_45", "14.40"),
    ("LIEF_034", "STS_0_32", "16.50"),
    ("LIEF_034", "STS_0_45", "19.50"),
    ("LIEF_034", "SCHOTTER_0_56", "13.50"),
    ("LIEF_034", "MG_B2_0_32", "17.50"),
    ("LIEF_034", "KIES_2_8", "17.10"),
    ("LIEF_034", "KIES_8_16", "18.50"),
    ("LIEF_034", "KIES_16_32", "16.90"),
    ("LIEF_034", "SAND_0_2", "12.40"),
    ("LIEF_034", "BRECHSAND_0_2", "13.90"),

    # LIEF_035 — Fichtelgebirgs-Granit GmbH (95444 Bayreuth)
    ("LIEF_035", "FSS_0_32", "18.50"),
    ("LIEF_035", "FSS_0_45", "15.80"),
    ("LIEF_035", "STS_0_32", "20.20"),
    ("LIEF_035", "STS_0_45", "15.90"),
    ("LIEF_035", "SCHOTTER_0_56", "12.60"),
    ("LIEF_035", "MG_B2_0_32", "20.60"),
    ("LIEF_035", "SPLITT_2_5", "24.20"),
    ("LIEF_035", "SPLITT_5_8", "20.70"),
    ("LIEF_035", "SPLITT_8_11", "25.60"),
    ("LIEF_035", "SPLITT_11_16", "22.50"),

    # LIEF_036 — Hofer Hartsteinwerk GmbH (95028 Hof)
    ("LIEF_036", "FSS_0_32", "17.90"),
    ("LIEF_036", "FSS_0_45", "13.60"),
    ("LIEF_036", "STS_0_32", "21.00"),
    ("LIEF_036", "STS_0_45", "15.70"),
    ("LIEF_036", "SCHOTTER_0_56", "15.90"),
    ("LIEF_036", "MG_B2_0_32", "19.30"),
    ("LIEF_036", "SPLITT_2_5", "23.60"),
    ("LIEF_036", "SPLITT_5_8", "24.10"),
    ("LIEF_036", "SPLITT_8_11", "25.50"),
    ("LIEF_036", "SPLITT_11_16", "20.20"),

    # LIEF_037 — Wunsiedler Granitwerk GmbH (95632 Wunsiedel)
    ("LIEF_037", "FSS_0_32", "14.70"),
    ("LIEF_037", "FSS_0_45", "15.60"),
    ("LIEF_037", "STS_0_32", "17.60"),
    ("LIEF_037", "STS_0_45", "16.00"),
    ("LIEF_037", "SCHOTTER_0_56", "13.00"),
    ("LIEF_037", "MG_B2_0_32", "17.00"),
    ("LIEF_037", "SPLITT_2_5", "22.60"),
    ("LIEF_037", "SPLITT_5_8", "22.40"),
    ("LIEF_037", "SPLITT_8_11", "21.40"),
    ("LIEF_037", "SPLITT_11_16", "23.30"),

    # LIEF_038 — Sechsämter Naturstein GmbH (95615 Marktredwitz)
    ("LIEF_038", "FSS_0_32", "15.50"),
    ("LIEF_038", "FSS_0_45", "15.50"),
    ("LIEF_038", "STS_0_32", "17.30"),
    ("LIEF_038", "STS_0_45", "17.20"),
    ("LIEF_038", "SCHOTTER_0_56", "12.40"),
    ("LIEF_038", "MG_B2_0_32", "18.10"),
    ("LIEF_038", "SPLITT_2_5", "21.20"),
    ("LIEF_038", "SPLITT_5_8", "25.30"),
    ("LIEF_038", "SPLITT_8_11", "23.00"),
    ("LIEF_038", "SPLITT_11_16", "19.70"),

    # LIEF_039 — Maintal Asphalt GmbH (96215 Lichtenfels)
    ("LIEF_039", "ASPHALT_AC32TS", "73.50"),
    ("LIEF_039", "ASPHALT_AC16BS", "95.00"),
    ("LIEF_039", "ASPHALT_AC11DS", "84.00"),
    ("LIEF_039", "SMA_8_S", "122.00"),
    ("LIEF_039", "BITUMEN_50_70", "586.00"),
    ("LIEF_039", "PMB_45_80", "874.00"),

    # LIEF_040 — Bamberger Baustoffe GmbH (96047 Bamberg)
    ("LIEF_040", "FSS_0_32", "18.10"),
    ("LIEF_040", "FSS_0_45", "15.00"),
    ("LIEF_040", "STS_0_32", "19.10"),
    ("LIEF_040", "STS_0_45", "19.00"),
    ("LIEF_040", "SCHOTTER_0_56", "16.40"),
    ("LIEF_040", "MG_B2_0_32", "18.70"),
    ("LIEF_040", "KIES_2_8", "19.20"),
    ("LIEF_040", "KIES_8_16", "17.50"),
    ("LIEF_040", "KIES_16_32", "16.10"),
    ("LIEF_040", "SAND_0_2", "13.00"),
    ("LIEF_040", "BRECHSAND_0_2", "14.80"),
    ("LIEF_040", "OBERBODEN", "6.30"),
    ("LIEF_040", "GROBK_BODEN", "9.20"),

    # LIEF_041 — Mainfranken Kies GmbH (97421 Schweinfurt)
    ("LIEF_041", "FSS_0_32", "14.40"),
    ("LIEF_041", "FSS_0_45", "16.50"),
    ("LIEF_041", "STS_0_32", "17.70"),
    ("LIEF_041", "STS_0_45", "16.30"),
    ("LIEF_041", "SCHOTTER_0_56", "12.70"),
    ("LIEF_041", "MG_B2_0_32", "21.50"),
    ("LIEF_041", "KIES_2_8", "19.40"),
    ("LIEF_041", "KIES_8_16", "17.30"),
    ("LIEF_041", "KIES_16_32", "14.50"),
    ("LIEF_041", "SAND_0_2", "12.40"),
    ("LIEF_041", "BRECHSAND_0_2", "14.50"),

    # LIEF_042 — Frankenwald Splitt GmbH (95119 Naila)
    ("LIEF_042", "FSS_0_32", "16.30"),
    ("LIEF_042", "FSS_0_45", "13.90"),
    ("LIEF_042", "STS_0_32", "18.80"),
    ("LIEF_042", "STS_0_45", "16.80"),
    ("LIEF_042", "SCHOTTER_0_56", "16.40"),
    ("LIEF_042", "MG_B2_0_32", "22.30"),

    # LIEF_043 — Oberharz Hartstein GmbH (38640 Goslar)
    ("LIEF_043", "FSS_0_32", "16.70"),
    ("LIEF_043", "FSS_0_45", "14.30"),
    ("LIEF_043", "STS_0_32", "21.60"),
    ("LIEF_043", "STS_0_45", "17.00"),
    ("LIEF_043", "SCHOTTER_0_56", "13.80"),
    ("LIEF_043", "MG_B2_0_32", "16.70"),
    ("LIEF_043", "SPLITT_2_5", "23.90"),
    ("LIEF_043", "SPLITT_5_8", "23.50"),
    ("LIEF_043", "SPLITT_8_11", "22.70"),
    ("LIEF_043", "SPLITT_11_16", "19.70"),

    # LIEF_044 — Söse Schotterwerk GmbH (37520 Osterode am Harz)
    ("LIEF_044", "FSS_0_32", "16.50"),
    ("LIEF_044", "FSS_0_45", "13.20"),
    ("LIEF_044", "STS_0_32", "17.70"),
    ("LIEF_044", "STS_0_45", "15.90"),
    ("LIEF_044", "SCHOTTER_0_56", "14.00"),
    ("LIEF_044", "MG_B2_0_32", "17.00"),
    ("LIEF_044", "SPLITT_2_5", "21.30"),
    ("LIEF_044", "SPLITT_5_8", "22.30"),
    ("LIEF_044", "SPLITT_8_11", "20.90"),
    ("LIEF_044", "SPLITT_11_16", "22.20"),

    # LIEF_045 — Südharz Naturstein GmbH (37412 Herzberg am Harz)
    ("LIEF_045", "FSS_0_32", "16.60"),
    ("LIEF_045", "FSS_0_45", "16.60"),
    ("LIEF_045", "STS_0_32", "19.90"),
    ("LIEF_045", "STS_0_45", "19.20"),
    ("LIEF_045", "SCHOTTER_0_56", "16.00"),
    ("LIEF_045", "MG_B2_0_32", "18.90"),
    ("LIEF_045", "SPLITT_2_5", "23.50"),
    ("LIEF_045", "SPLITT_5_8", "27.00"),
    ("LIEF_045", "SPLITT_8_11", "20.30"),
    ("LIEF_045", "SPLITT_11_16", "23.00"),

    # LIEF_046 — Seesen Kies & Asphalt GmbH (38723 Seesen)
    ("LIEF_046", "ASPHALT_AC32TS", "77.50"),
    ("LIEF_046", "ASPHALT_AC16BS", "73.00"),
    ("LIEF_046", "ASPHALT_AC11DS", "104.00"),
    ("LIEF_046", "SMA_8_S", "124.00"),
    ("LIEF_046", "BITUMEN_50_70", "620.00"),
    ("LIEF_046", "PMB_45_80", "935.00"),

    # LIEF_047 — Leinetal Kieswerk GmbH (37154 Northeim)
    ("LIEF_047", "FSS_0_32", "18.00"),
    ("LIEF_047", "FSS_0_45", "13.80"),
    ("LIEF_047", "STS_0_32", "19.20"),
    ("LIEF_047", "STS_0_45", "18.00"),
    ("LIEF_047", "SCHOTTER_0_56", "15.80"),
    ("LIEF_047", "MG_B2_0_32", "21.30"),
    ("LIEF_047", "KIES_2_8", "19.20"),
    ("LIEF_047", "KIES_8_16", "16.90"),
    ("LIEF_047", "KIES_16_32", "17.20"),
    ("LIEF_047", "SAND_0_2", "14.10"),
    ("LIEF_047", "BRECHSAND_0_2", "16.30"),

    # LIEF_048 — Göttinger Baustoff-Recycling GmbH (37073 Göttingen)
    ("LIEF_048", "FSS_0_32", "15.20"),
    ("LIEF_048", "FSS_0_45", "13.30"),
    ("LIEF_048", "STS_0_32", "17.00"),
    ("LIEF_048", "STS_0_45", "17.30"),
    ("LIEF_048", "SCHOTTER_0_56", "12.80"),
    ("LIEF_048", "MG_B2_0_32", "21.50"),
    ("LIEF_048", "RC_SCHOTTER_0_45", "9.40"),
    ("LIEF_048", "RC_0_32", "8.50"),
    ("LIEF_048", "OBERBODEN", "7.50"),
    ("LIEF_048", "GROBK_BODEN", "10.80"),

    # LIEF_049 — Einbeck Schotter & Sand GmbH (37574 Einbeck)
    ("LIEF_049", "FSS_0_32", "16.40"),
    ("LIEF_049", "FSS_0_45", "13.20"),
    ("LIEF_049", "STS_0_32", "20.70"),
    ("LIEF_049", "STS_0_45", "19.30"),
    ("LIEF_049", "SCHOTTER_0_56", "14.40"),
    ("LIEF_049", "MG_B2_0_32", "19.80"),
    ("LIEF_049", "KIES_2_8", "18.30"),
    ("LIEF_049", "KIES_8_16", "14.40"),
    ("LIEF_049", "KIES_16_32", "16.50"),
    ("LIEF_049", "SAND_0_2", "12.40"),
    ("LIEF_049", "BRECHSAND_0_2", "13.50"),

    # LIEF_050 — Oberharzer Bergwerks-Baustoffe GmbH (38678 Clausthal-Zellerfeld)
    ("LIEF_050", "FSS_0_32", "15.40"),
    ("LIEF_050", "FSS_0_45", "16.50"),
    ("LIEF_050", "STS_0_32", "17.40"),
    ("LIEF_050", "STS_0_45", "19.30"),
    ("LIEF_050", "SCHOTTER_0_56", "16.40"),
    ("LIEF_050", "MG_B2_0_32", "19.50"),
    ("LIEF_050", "KIES_2_8", "16.90"),
    ("LIEF_050", "KIES_8_16", "16.40"),
    ("LIEF_050", "KIES_16_32", "16.30"),
    ("LIEF_050", "SAND_0_2", "14.40"),
    ("LIEF_050", "BRECHSAND_0_2", "16.00"),
    ("LIEF_050", "OBERBODEN", "7.50"),
    ("LIEF_050", "GROBK_BODEN", "9.00"),

    # LIEF_051 — Braunschweiger Asphaltmischwerk GmbH (38112 Braunschweig)
    ("LIEF_051", "ASPHALT_AC32TS", "66.50"),
    ("LIEF_051", "ASPHALT_AC16BS", "78.50"),
    ("LIEF_051", "ASPHALT_AC11DS", "101.50"),
    ("LIEF_051", "SMA_8_S", "105.00"),
    ("LIEF_051", "BITUMEN_50_70", "609.00"),
    ("LIEF_051", "PMB_45_80", "751.00"),

    # LIEF_052 — Innerste Kies & Sand GmbH (31135 Hildesheim)
    ("LIEF_052", "FSS_0_32", "14.40"),
    ("LIEF_052", "FSS_0_45", "14.40"),
    ("LIEF_052", "STS_0_32", "20.00"),
    ("LIEF_052", "STS_0_45", "19.00"),
    ("LIEF_052", "SCHOTTER_0_56", "15.20"),
    ("LIEF_052", "MG_B2_0_32", "18.40"),
    ("LIEF_052", "KIES_2_8", "17.60"),
    ("LIEF_052", "KIES_8_16", "16.30"),
    ("LIEF_052", "KIES_16_32", "15.30"),
    ("LIEF_052", "SAND_0_2", "11.90"),
    ("LIEF_052", "BRECHSAND_0_2", "17.20"),
]


def lade_preise(baustoffe: dict, lieferanten: dict, stichtag: date = date(2026, 1, 1)) -> int:
    """Attach the static prices to the supplier objects. Idempotent."""
    for lief in lieferanten.values():
        lief.preise.clear()
    for lcode, bcode, preis in PREISE:
        lieferanten[lcode].preise.append(
            BaustoffPreis(baustoff_id=baustoffe[bcode].id, preis_eur_pro_t=D(preis), gueltig_ab=stichtag))
    return len(PREISE)


if __name__ == "__main__":
    print(f"{len(PREISE)} Preiszeilen · "
          f"{len({p[0] for p in PREISE})} Lieferanten · "
          f"{len({p[1] for p in PREISE})} Materialien")