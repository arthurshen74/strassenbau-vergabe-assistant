"""
materialien.py — canonical Baustoff catalog for road/construction work, plus
realistic per-supplier assortments and prices.

Single source of truth for materials. Store.py imports BAUSTOFFE from here.
`bestuecke()` gives each Lieferant a price list matching its TYPE (read from the
firm name): a Kieswerk carries Kies/Sand, an Asphaltmischwerk carries mixes +
bitumen, a Schotter-/Hartsteinwerk carries crushed stone + Splitt, etc. Prices
vary ±~15 % per supplier around a base list price. All numbers are plausible
prototype values (€/t, 2026 ballpark) — replace with real quotes.
"""

from __future__ import annotations

from datetime import date

from model import Baustoff, D
from lieferanten import LIEFERANTEN, entfernung_km
from lieferanten_preise import lade_preise

STICHTAG = date(2026, 6, 22)
TRANSPORT_EUR_PRO_T_KM = D("0.12")          # for delivered-price comparison

# Kategorien
MINERAL = "Mineralische Tragschicht"
KIES = "Kies/Sand"
SPLITT = "Splitt"
RECYCLING = "Recycling"
ASPHALT = "Asphaltmischgut"
BINDEMITTEL = "Bindemittel"
BODEN = "Boden"

# (code, name, kategorie, koernung, rohdichte, verdichtung, basispreis €/t)
_DEF = [
    ("FSS_0_32",  "Frostschutzschicht 0/32",        MINERAL, "0/32", "2.00", "1.10", "16.00"),
    ("FSS_0_45",  "Frostschutzschicht 0/45",        MINERAL, "0/45", "2.00", "1.10", "15.00"),
    ("STS_0_32",  "Schottertragschicht 0/32",       MINERAL, "0/32", "2.05", "1.12", "18.50"),
    ("STS_0_45",  "Schottertragschicht 0/45",       MINERAL, "0/45", "2.05", "1.12", "17.50"),
    ("SCHOTTER_0_56", "Schotter 0/56",              MINERAL, "0/56", "2.00", "1.10", "14.00"),
    ("MG_B2_0_32", "Mineralgemisch B2 0/32",        MINERAL, "0/32", "2.00", "1.12", "19.00"),
    ("KIES_2_8",  "Kies 2/8",                        KIES, "2/8",   "1.85", "1.05", "17.00"),
    ("KIES_8_16", "Kies 8/16",                       KIES, "8/16",  "1.85", "1.05", "16.00"),
    ("KIES_16_32", "Kies 16/32",                     KIES, "16/32", "1.85", "1.05", "15.00"),
    ("SAND_0_2",  "Natursand 0/2",                   KIES, "0/2",   "1.60", "1.00", "13.00"),
    ("BRECHSAND_0_2", "Brechsand 0/2",               KIES, "0/2",   "1.65", "1.00", "15.00"),
    ("SPLITT_2_5", "Splitt 2/5",                     SPLITT, "2/5", "1.50", "1.00", "24.00"),
    ("SPLITT_5_8", "Splitt 5/8",                     SPLITT, "5/8", "1.50", "1.00", "23.00"),
    ("SPLITT_8_11", "Splitt 8/11",                   SPLITT, "8/11", "1.50", "1.00", "22.00"),
    ("SPLITT_11_16", "Splitt 11/16",                 SPLITT, "11/16", "1.50", "1.00", "21.00"),
    ("RC_SCHOTTER_0_45", "RC-Schotter 0/45",         RECYCLING, "0/45", "1.90", "1.08", "9.00"),
    ("RC_0_32",   "RC-Mineralgemisch 0/32",          RECYCLING, "0/32", "1.90", "1.08", "8.00"),
    ("ASPHALT_AC32TS", "Asphalttragschicht AC 32 T S", ASPHALT, None, "2.40", "1.00", "72.00"),
    ("ASPHALT_AC16BS", "Asphaltbinder AC 16 B S",    ASPHALT, None, "2.45", "1.00", "82.00"),
    ("ASPHALT_AC11DS", "Asphaltdeckschicht AC 11 D S", ASPHALT, None, "2.45", "1.00", "92.00"),
    ("SMA_8_S",   "Splittmastixasphalt SMA 8 S",     ASPHALT, None, "2.45", "1.00", "108.00"),
    ("BITUMEN_50_70", "Straßenbaubitumen 50/70",     BINDEMITTEL, None, "1.03", "1.00", "580.00"),
    ("PMB_45_80", "Polymermod. Bitumen 45/80-50",    BINDEMITTEL, None, "1.02", "1.00", "850.00"),
    ("OBERBODEN", "Oberboden",                       BODEN, None, "1.50", "1.00", "7.00"),
    ("GROBK_BODEN", "Grobkörniger Boden",            BODEN, None, "1.90", "1.05", "10.00"),
    ("BODEN_KL_3_5", "Boden Klasse 3–5 (Aushub, LAGA Z2)", BODEN, None, "1.95", "1.00", None),  # Aushub, kein Verkauf
]

BAUSTOFFE: dict[str, Baustoff] = {
    code: Baustoff(code=code, name=name, kategorie=kat, koernung=koern,
                   rohdichte_t_pro_m3=D(dichte), verdichtungsfaktor=D(verd),
                   basispreis_eur_pro_t=D(preis) if preis else None)
    for (code, name, kat, koern, dichte, verd, preis) in _DEF
}


# --------------------------------------------------------------------------- #
# Map a supplier's name to the categories it carries
# --------------------------------------------------------------------------- #
def _kategorien_fuer(firmenname: str) -> set[str]:
    n = firmenname.lower()
    if "asphalt" in n or "mischwerk" in n:
        return {ASPHALT, BINDEMITTEL}
    if "recycling" in n:
        return {RECYCLING, MINERAL, BODEN}
    if "kies" in n or "sand" in n:
        return {KIES, MINERAL}
    if any(w in n for w in ("schotter", "hartstein", "naturstein", "diabas", "granit")):
        return {MINERAL, SPLITT}
    if "mineralgemisch" in n or "baustoff" in n:
        return {MINERAL, KIES, BODEN}
    return {MINERAL}


# Prices are now STATIC — see lieferanten_preise.py; load with lade_preise(BAUSTOFFE, LIEFERANTEN).
# _kategorien_fuer above documents how that static list was originally seeded per supplier type.


def guenstigster_lieferant(baustoff_code: str, lat: float, lon: float):
    """Cheapest DELIVERED (price + transport·distance) supplier for a material."""
    bid = BAUSTOFFE[baustoff_code].id
    angebote = []
    for lief in LIEFERANTEN.values():
        preis = lief.preis_fuer(bid, STICHTAG)
        if preis is None:
            continue
        km = D(str(round(entfernung_km(lief, lat, lon), 1)))
        frei_bau = (preis + TRANSPORT_EUR_PRO_T_KM * km).quantize(D("0.01"))
        angebote.append((lief, preis, km, frei_bau))
    return sorted(angebote, key=lambda t: t[3])


if __name__ == "__main__":
    lade_preise(BAUSTOFFE, LIEFERANTEN)
    print(f"{len(BAUSTOFFE)} Materialien im Katalog. Lieferantensortimente bestückt.\n")
    fss = sum(1 for l in LIEFERANTEN.values() if l.preis_fuer(BAUSTOFFE['FSS_0_32'].id, STICHTAG))
    asp = sum(1 for l in LIEFERANTEN.values() if l.preis_fuer(BAUSTOFFE['ASPHALT_AC32TS'].id, STICHTAG))
    print(f"Lieferanten mit FSS 0/32: {fss} · mit Asphalt AC 32 T S: {asp}\n")

    site = (51.42, 10.81)
    print(f"Günstigste FSS 0/32 frei Baustelle {site} (Werkspreis + Transport):\n")
    print(f"{'Code':<10}{'Werk':<22}{'Werk €/t':>9}{'km':>7}{'frei Bau €/t':>14}")
    print("-" * 62)
    for lief, preis, km, frei in guenstigster_lieferant("FSS_0_32", *site)[:6]:
        ort = lief.standort.split(", ")[1]
        print(f"{lief.code:<10}{ort:<22}{preis:>9}{km:>7}{frei:>14}")