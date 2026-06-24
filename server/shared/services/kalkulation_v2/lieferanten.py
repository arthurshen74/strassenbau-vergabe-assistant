"""
lieferanten.py — fictional Baustofflieferanten at REAL, geocodable locations.

Company names are invented; the towns, postal codes and coordinates are real so
you can geocode the `standort` strings and run distance calculations. Weighting:
Thüringen (heaviest, around Nordhausen/Harz), Sachsen-Anhalt, Nordbayern,
Niedersachsen.

CAVEAT: coordinates are from memory and good to ~1–3 km (small towns maybe more).
For production, let your geocoder resolve the `standort` address string — that is
the authoritative key; treat the embedded lat/lon as a convenience/fallback.
Distances here are HAVERSINE (great-circle); real haul distance is road distance —
apply a detour factor (~1.3×) or swap in OSRM/Google routing.
"""

from __future__ import annotations

import math

from shared.services.kalkulation_v2.model import Baustofflieferant, BaustoffPreis, D

# (code, Firmenname, Straße, PLZ, Ort, lat, lon)
_DATA = [
    # --- Thüringen ---
    ("LIEF_001", "Harzland Schotter & Splitt GmbH", "Am Steinbruch 3", "99734", "Nordhausen", 51.503, 10.792),
    ("LIEF_002", "Kyffhäuser Naturstein GmbH", "Industriestraße 14", "99706", "Sondershausen", 51.367, 10.870),
    ("LIEF_003", "Unstrut Kies & Sand GmbH", "Zum Kieswerk 1", "99974", "Mühlhausen", 51.209, 10.453),
    ("LIEF_004", "Thüringer Mineralgemisch GmbH", "Gewerbering 7", "99610", "Sömmerda", 51.160, 11.117),
    ("LIEF_005", "Mitteldeutsche Baustoffe AG", "Schmidtstedter Weg 22", "99086", "Erfurt", 50.978, 11.029),
    ("LIEF_006", "Gothaer Hartsteinwerk GmbH", "Steinweg 9", "99867", "Gotha", 50.948, 10.703),
    ("LIEF_007", "Wartburg Asphaltmischwerk GmbH", "Am Mischwerk 2", "99817", "Eisenach", 50.974, 10.319),
    ("LIEF_008", "Salza Kieswerk GmbH", "Kieswerkstraße 5", "99947", "Bad Langensalza", 51.108, 10.646),
    ("LIEF_009", "Eichsfeld Naturstein GmbH", "Industrieweg 11", "37308", "Heilbad Heiligenstadt", 51.378, 10.137),
    ("LIEF_010", "Arnstädter Schotterwerk GmbH", "Am Steinfeld 4", "99310", "Arnstadt", 50.834, 10.945),
    ("LIEF_011", "Ilm-Kies GmbH", "An der Ilm 8", "98693", "Ilmenau", 50.683, 10.918),
    ("LIEF_012", "Rennsteig Hartstein GmbH", "Bergstraße 17", "98527", "Suhl", 50.609, 10.691),
    ("LIEF_013", "Südthüringer Baustoff-Recycling GmbH", "Recyclinghof 1", "98617", "Meiningen", 50.569, 10.415),
    ("LIEF_014", "Saale Splitt & Schotter GmbH", "Saalstraße 30", "07318", "Saalfeld", 50.650, 11.365),
    ("LIEF_015", "Schwarzatal Naturstein GmbH", "Im Gewerbegebiet 6", "07407", "Rudolstadt", 50.721, 11.339),
    ("LIEF_016", "Saaletal Asphalt GmbH", "Löbstedter Straße 80", "07745", "Jena", 50.927, 11.586),
    ("LIEF_017", "Elstertal Kies & Beton GmbH", "Leipziger Straße 120", "07545", "Gera", 50.881, 12.082),
    ("LIEF_018", "Frankenwald-Grenze Schotter GmbH", "Bahnhofstraße 45", "96515", "Sonneberg", 50.357, 11.174),
    # --- Sachsen-Anhalt ---
    ("LIEF_019", "Goldene Aue Kieswerk GmbH", "Kiesgrubenweg 2", "06526", "Sangerhausen", 51.472, 11.297),
    ("LIEF_020", "Mansfelder Hartstein GmbH", "Am Tagebau 9", "06295", "Lutherstadt Eisleben", 51.527, 11.547),
    ("LIEF_021", "Harzvorland Naturstein GmbH", "Quarmbecker Weg 3", "06484", "Quedlinburg", 51.788, 11.137),
    ("LIEF_022", "Halberstädter Schotterwerk GmbH", "Gröperstraße 60", "38820", "Halberstadt", 51.896, 11.048),
    ("LIEF_023", "Brocken Diabas GmbH", "Diabasweg 1", "38855", "Wernigerode", 51.834, 10.785),
    ("LIEF_024", "Bodetal Hartstein GmbH", "Im Bruch 4", "06502", "Thale", 51.748, 11.043),
    ("LIEF_025", "Aschersleben Baustoffe GmbH", "Güstener Straße 14", "06449", "Aschersleben", 51.752, 11.461),
    ("LIEF_026", "Bode Kies & Sand GmbH", "Förderstedter Straße 25", "39418", "Staßfurt", 51.853, 11.583),
    ("LIEF_027", "Saale-Elbe Mineralstoffe GmbH", "Hafenstraße 7", "06406", "Bernburg", 51.793, 11.739),
    ("LIEF_028", "Saalekreis Asphaltmischwerk GmbH", "Merseburger Straße 200", "06112", "Halle (Saale)", 51.482, 11.969),
    ("LIEF_029", "Saale-Unstrut Schotter GmbH", "Weinbergweg 12", "06618", "Naumburg", 51.150, 11.809),
    ("LIEF_030", "Weißenfelser Kieswerk GmbH", "Kiesweg 5", "06667", "Weißenfels", 51.200, 11.967),
    ("LIEF_031", "Elbe Baustoff-Recycling GmbH", "Hafenstraße 55", "39104", "Magdeburg", 52.131, 11.639),
    # --- Nordbayern (Ober-/Unterfranken, Oberpfalz) ---
    ("LIEF_032", "Coburger Land Schotter GmbH", "Rodacher Straße 70", "96450", "Coburg", 50.258, 10.965),
    ("LIEF_033", "Frankenwald Diabaswerk GmbH", "Am Diabasbruch 2", "96317", "Kronach", 50.241, 11.330),
    ("LIEF_034", "Weißmain Kies & Sand GmbH", "Mainaustraße 18", "95326", "Kulmbach", 50.103, 11.451),
    ("LIEF_035", "Fichtelgebirgs-Granit GmbH", "Granitweg 4", "95444", "Bayreuth", 49.948, 11.578),
    ("LIEF_036", "Hofer Hartsteinwerk GmbH", "Saalestraße 33", "95028", "Hof", 50.318, 11.918),
    ("LIEF_037", "Wunsiedler Granitwerk GmbH", "Am Steinbruch 1", "95632", "Wunsiedel", 50.041, 12.001),
    ("LIEF_038", "Sechsämter Naturstein GmbH", "Industriestraße 9", "95615", "Marktredwitz", 50.001, 12.087),
    ("LIEF_039", "Maintal Asphalt GmbH", "Coburger Straße 110", "96215", "Lichtenfels", 50.146, 11.058),
    ("LIEF_040", "Bamberger Baustoffe GmbH", "Hafenstraße 20", "96047", "Bamberg", 49.891, 10.887),
    ("LIEF_041", "Mainfranken Kies GmbH", "Hafenstraße 5", "97421", "Schweinfurt", 50.049, 10.227),
    ("LIEF_042", "Frankenwald Splitt GmbH", "Selbitzer Straße 6", "95119", "Naila", 50.329, 11.703),
    # --- Niedersachsen (südlich, Harz/Leinetal) ---
    ("LIEF_043", "Oberharz Hartstein GmbH", "Bergstraße 40", "38640", "Goslar", 51.906, 10.429),
    ("LIEF_044", "Söse Schotterwerk GmbH", "Sösetalstraße 3", "37520", "Osterode am Harz", 51.728, 10.252),
    ("LIEF_045", "Südharz Naturstein GmbH", "Sieber Straße 8", "37412", "Herzberg am Harz", 51.658, 10.342),
    ("LIEF_046", "Seesen Kies & Asphalt GmbH", "Industriestraße 12", "38723", "Seesen", 51.893, 10.178),
    ("LIEF_047", "Leinetal Kieswerk GmbH", "Am Leinekanal 2", "37154", "Northeim", 51.706, 9.994),
    ("LIEF_048", "Göttinger Baustoff-Recycling GmbH", "Rudolf-Wissell-Straße 14", "37073", "Göttingen", 51.534, 9.935),
    ("LIEF_049", "Einbeck Schotter & Sand GmbH", "Hansestraße 7", "37574", "Einbeck", 51.821, 9.868),
    ("LIEF_050", "Oberharzer Bergwerks-Baustoffe GmbH", "Erzstraße 1", "38678", "Clausthal-Zellerfeld", 51.808, 10.339),
    ("LIEF_051", "Braunschweiger Asphaltmischwerk GmbH", "Hansestraße 60", "38112", "Braunschweig", 52.265, 10.527),
    ("LIEF_052", "Innerste Kies & Sand GmbH", "Senkingstraße 9", "31135", "Hildesheim", 52.150, 9.951),
]

LIEFERANTEN: dict[str, Baustofflieferant] = {
    code: Baustofflieferant(
        code=code, name=name,
        standort=f"{strasse}, {plz} {ort}, Deutschland",
        breitengrad=D(str(lat)), laengengrad=D(str(lon)),
    )
    for (code, name, strasse, plz, ort, lat, lon) in _DATA
}


# --------------------------------------------------------------------------- #
# Distance helpers
# --------------------------------------------------------------------------- #
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def entfernung_km(lief: Baustofflieferant, lat: float, lon: float, detour: float = 1.3) -> float:
    """Approx. road distance: haversine × detour factor (default 1.3)."""
    return haversine_km(float(lief.breitengrad), float(lief.laengengrad), lat, lon) * detour # type: ignore


def naechste_lieferanten(lat: float, lon: float, n: int = 10) -> list[tuple[Baustofflieferant, float]]:
    ranked = sorted(((l, entfernung_km(l, lat, lon)) for l in LIEFERANTEN.values()), key=lambda t: t[1])
    return ranked[:n]


def attach_prices(baustoffe: dict, seed: int = 42) -> None:
    """Optional: give each supplier plausible prices for a random subset of materials.
    Pass Store.BAUSTOFFE. Prices are illustrative."""
    import random
    from datetime import date
    rng = random.Random(seed)
    basis = {"GROBK_BODEN": 9.5, "MG_B2_0_32": 19.0, "OBERBODEN": 7.0, "BODEN_KL_3_5": 0.0}
    for lief in LIEFERANTEN.values():
        for code, b in baustoffe.items():
            if rng.random() < 0.6:  # not every supplier carries every material
                grund = basis.get(code, 15.0)
                preis = round(grund * rng.uniform(0.9, 1.2), 2) if grund else 0.0
                lief.preise.append(BaustoffPreis(baustoff_id=b.id, preis_eur_pro_t=D(str(preis)),
                                                 gueltig_ab=date(2026, 1, 1)))


if __name__ == "__main__":
    # Example: a Baustelle on the L 101 near Nordhausen/Sondershausen
    site_lat, site_lon, site_name = 51.42, 10.81, "Baustelle L 101 (Beispiel)"
    print(f"{len(LIEFERANTEN)} Lieferanten · nächste 10 zu {site_name} ({site_lat}, {site_lon}):\n")
    print(f"{'Code':<10}{'Firma':<40}{'Ort':<22}{'~Straße km':>11}")
    print("-" * 84)
    for lief, km in naechste_lieferanten(site_lat, site_lon, 10):
        ort = lief.standort.split(", ")[1] # type: ignore
        print(f"{lief.code:<10}{lief.name[:38]:<40}{ort:<22}{km:>11.1f}")