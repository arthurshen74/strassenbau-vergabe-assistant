"""
betriebsarten.py — the operation taxonomy (Betriebskategorie + Betriebsart) as data.

A machine carries one productivity Leistungsprofil per Betriebsart; a Vorgang names the
Betriebsart it runs. Both are referenced by string code, so the taxonomy can be edited
(add/rename a mode or a category) WITHOUT recompiling — only AufloesungsMethode/Kostenart
stay compiled. The set below is calibrated to the real LV wording (Farbe vs Plastik
Demarkierung, depth-banded Trennen, Naht/Anschluss joints, …).

Validated at import: every Betriebsart points at a known Betriebskategorie. Exports
BETRIEBSKATEGORIEN, BETRIEBSARTEN, betriebsarten_der_kategorie(), validate().
"""

from shared.services.kalkulation_v2.model import Betriebsart, Betriebskategorie

BETRIEBSKATEGORIEN: dict[str, Betriebskategorie] = {
    k.code: k
    for k in [
        Betriebskategorie(code="fraesen", bezeichnung="Fräsen"),
        Betriebskategorie(code="demarkierung", bezeichnung="Demarkierung (Markierung entfernen)"),
        Betriebskategorie(code="trennen", bezeichnung="Trennen / Schneiden"),
        Betriebskategorie(code="abbruch", bezeichnung="Abbruch / Aufnehmen"),
        Betriebskategorie(code="erdbau", bezeichnung="Erdbau / Planum"),
        Betriebskategorie(code="verdichtung", bezeichnung="Verdichtung"),
        Betriebskategorie(code="einbau", bezeichnung="Einbau"),
        Betriebskategorie(code="reinigung", bezeichnung="Reinigung"),
        Betriebskategorie(code="anspritzen", bezeichnung="Anspritzen / Schichtenverbund"),
        Betriebskategorie(code="abstreuen", bezeichnung="Abstreuen / Abstumpfen"),
        Betriebskategorie(code="fugen", bezeichnung="Fugen / Nähte"),
    ]
}


def _ba(code: str, bez: str, kat: str, einheit: str) -> Betriebsart:
    return Betriebsart(code=code, bezeichnung=bez, kategorie_code=kat, einheit=einheit)


BETRIEBSARTEN: dict[str, Betriebsart] = {
    b.code: b
    for b in [
        # Fräsen
        _ba("regelfraesen", "Regelfräsen", "fraesen", "m2/h"),
        _ba("feinfraesen", "Feinfräsen", "fraesen", "m2/h"),
        # Demarkierung (Markierung entfernen) — material/method-specific productivity
        _ba("demark_farbe", "Demarkierung Farbe", "demarkierung", "m/h"),
        _ba("demark_plastik", "Demarkierung Plastik/Thermoplast", "demarkierung", "m/h"),
        _ba("demark_hochdruck", "Demarkierung Hochdruckwasser", "demarkierung", "m/h"),
        # Trennen / Schneiden
        _ba("asphalt_schneiden", "Asphaltbefestigung trennen/schneiden", "trennen", "m/h"),
        _ba("fuge_aufweiten", "Fuge/Naht aufweiten (schneiden)", "trennen", "m/h"),
        # Abbruch
        _ba("asphalt_aufbrechen", "Asphalt aufbrechen und aufnehmen", "abbruch", "m2/h"),
        _ba("boden_abtragen", "Boden/Bankett abtragen und schälen", "abbruch", "m3/h"),
        # Erdbau / Planum
        _ba("planum_herstellen", "Planum herstellen", "erdbau", "m2/h"),
        _ba("schuettgut_einbau", "Schüttgut liefern und legen", "erdbau", "m3/h"),
        _ba("profilieren", "Profilieren / auf Höhe abziehen", "erdbau", "m2/h"),
        _ba("oberboden_andecken", "Oberboden andecken", "erdbau", "m2/h"),
        # Verdichtung
        _ba("verdichten_flaeche", "Verdichten (flächig)", "verdichtung", "m2/h"),
        _ba("verdichten_uebergang", "Verdichten (je Walzübergang)", "verdichtung", "m2/h"),
        _ba("bankett_verdichten", "Bankett verdichten (kl. Tandemwalze)", "verdichtung", "m2/h"),
        # Einbau
        _ba("asphalt_einbau", "Asphaltschicht einbauen (Einbauzug)", "einbau", "t/h"),
        _ba("asphalt_handeinbau", "Asphaltschicht im Handeinbau (Kleinflächen)", "einbau", "m2/h"),
        _ba("gussasphalt_einbau", "Gussasphaltschicht einbauen (Fertiger/Kocher)", "einbau", "m2/h"),
        _ba("dsk_einbau", "Dünnschichtbelag im Kalteinbau (DSK)", "einbau", "m2/h"),
        _ba("bankett_einbau", "Bankett liefern/legen/profilieren (Fertiger)", "einbau", "m2/h"),
        _ba("einlage_verlegen", "Asphalteinlage verlegen", "einbau", "m2/h"),
        # Reinigung
        _ba("kehren", "Unterlage reinigen (Kehrmaschine)", "reinigung", "m2/h"),
        _ba("hochdruckreinigen", "Unterlage reinigen (HD-Wasch-Saug)", "reinigung", "m2/h"),
        # Anspritzen
        _ba("anspritzen", "Bitumenemulsion aufsprühen (Schichtenverbund)", "anspritzen", "m2/h"),
        # Abstreuen
        _ba("abstreuen", "Abstumpfung aufbringen und einwalzen", "abstreuen", "m2/h"),
        # Fugen / Nähte
        _ba("fugenverguss", "Fugenfüllung herstellen (Fugenmasse)", "fugen", "m/h"),
        _ba("naht_herstellen", "Naht in Asphaltschicht herstellen", "fugen", "m/h"),
        _ba("randabdichtung", "Randabdichtung/Nahtabdichtung (Fugenband/Randmasse)", "fugen", "m/h"),
    ]
}


def betriebsarten_der_kategorie(kategorie_code: str) -> list[Betriebsart]:
    return [b for b in BETRIEBSARTEN.values() if b.kategorie_code == kategorie_code]


def validate() -> list[str]:
    fehler: list[str] = []
    for b in BETRIEBSARTEN.values():
        if b.kategorie_code not in BETRIEBSKATEGORIEN:
            fehler.append(f"Betriebsart '{b.code}' -> unbekannte Kategorie '{b.kategorie_code}'")
    return fehler


_fehler = validate()
if _fehler:
    raise ValueError("Ungültige Betriebsart-Taxonomie:\n  " + "\n  ".join(_fehler))


if __name__ == "__main__":
    print(f"{len(BETRIEBSKATEGORIEN)} Kategorien, {len(BETRIEBSARTEN)} Betriebsarten:")
    for kat in BETRIEBSKATEGORIEN.values():
        arten = betriebsarten_der_kategorie(kat.code)
        print(f"  {kat.bezeichnung} ({kat.code}): {', '.join(b.code for b in arten)}")
