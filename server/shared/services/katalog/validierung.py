"""Bundle validation (§7) — pure rules over the active catalog + the bundle's own keys.

`lade_stand` reads the active catalog into a `KatalogStand` (the only I/O); `pruefe_bundle` is a
pure function of (bundle, stand) returning a `BundleBericht`. The six rules mirror §7:

1. every bundle Formel parses and references only known variables;
2. the formula dependency graph (active ∪ bundle) is acyclic;
3. every Vorgang cost variable is producible (has a FORMEL/KONSTANTE/STAMMDATEN step, or is a
   kontext-gruppe variable, or is a formula output);
4. every code reference resolves (Ausführungsart/Betriebsart/Kategorie/Vorgang/Leistung/Bauverfahren);
5. a bundle variable does not newly shadow an active variable of a different gruppe (the KATALOG
   merge would resolve the collision silently);
6. a bundle key equal to an active key is reported as a supersede (an update, not an error).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from shared.models.katalog import BundleBericht, KatalogEntitaet, RezeptBundle, VariablenGruppe
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.model import AufloesungsMethode, Formel, VariableDefinition

# Resolution methods that let the Kalkulator produce a value deterministically (no StateGraph).
_PRODUZIERENDE_METHODEN = {
    AufloesungsMethode.FORMEL,
    AufloesungsMethode.KONSTANTE,
    AufloesungsMethode.STAMMDATEN,
}


@dataclass
class KatalogStand:
    """A snapshot of the active catalog, sufficient to validate a bundle without further I/O."""

    known_var_namen: set[str] = field(default_factory=set)
    produzierbare_namen: set[str] = field(default_factory=set)
    var_gruppen: dict[str, set[VariablenGruppe]] = field(default_factory=lambda: defaultdict(set))
    formeln: dict[str, Formel] = field(default_factory=dict)
    globale_namen: set[str] = field(default_factory=set)
    leistung_codes: set[str] = field(default_factory=set)
    bauverfahren_codes: set[str] = field(default_factory=set)
    vorgang_codes: set[str] = field(default_factory=set)
    ausfuehrungsart_codes: set[str] = field(default_factory=set)
    betriebsart_codes: set[str] = field(default_factory=set)
    betriebskategorie_codes: set[str] = field(default_factory=set)
    baustoff_codes: set[str] = field(default_factory=set)
    maschinen_codes: set[str] = field(default_factory=set)


def _ist_produzierbar(gruppe: VariablenGruppe, definition: VariableDefinition) -> bool:
    if gruppe == VariablenGruppe.KONTEXT:
        return True
    return any(s.methode in _PRODUZIERENDE_METHODEN for s in definition.aufloesung)


async def lade_stand(repo: KatalogRepository) -> KatalogStand:
    """Read the active catalog into a KatalogStand (the validator's only I/O)."""
    stand = KatalogStand()

    for z in await repo.aktive(KatalogEntitaet.VARIABLEN):
        name = z.schluessel
        gruppe = VariablenGruppe(z.payload["gruppe"])
        stand.known_var_namen.add(name)
        stand.var_gruppen[name].add(gruppe)
        rest = {k: v for k, v in z.payload.items() if k != "gruppe"}
        definition = VariableDefinition.model_validate({"name": name, **rest})
        if _ist_produzierbar(gruppe, definition):
            stand.produzierbare_namen.add(name)

    for z in await repo.aktive(KatalogEntitaet.FORMELN):
        stand.formeln[z.schluessel] = Formel.model_validate({"name": z.schluessel, **z.payload})

    async def codes(entitaet: KatalogEntitaet) -> set[str]:
        return {z.schluessel for z in await repo.aktive(entitaet)}

    stand.globale_namen = await codes(KatalogEntitaet.GLOBALE_VARIABLEN)
    stand.leistung_codes = await codes(KatalogEntitaet.LEISTUNGEN)
    stand.bauverfahren_codes = await codes(KatalogEntitaet.BAUVERFAHREN)
    stand.vorgang_codes = await codes(KatalogEntitaet.VORGAENGE)
    stand.ausfuehrungsart_codes = await codes(KatalogEntitaet.AUSFUEHRUNGSARTEN)
    stand.betriebsart_codes = await codes(KatalogEntitaet.BETRIEBSARTEN)
    stand.betriebskategorie_codes = await codes(KatalogEntitaet.BETRIEBSKATEGORIEN)
    stand.baustoff_codes = await codes(KatalogEntitaet.BAUSTOFFE)
    stand.maschinen_codes = await codes(KatalogEntitaet.MASCHINEN)
    return stand


def _hat_zyklus(formeln: dict[str, Formel]) -> list[str]:
    """Return one cycle of formula names if the dependency graph has one, else []."""
    kanten: dict[str, set[str]] = {}
    for name, formel in formeln.items():
        try:
            eingaben = formel.eingaben()
        except SyntaxError:
            eingaben = set()
        kanten[name] = {e for e in eingaben if e in formeln}

    WEISS, GRAU, SCHWARZ = 0, 1, 2
    farbe = dict.fromkeys(formeln, WEISS)
    pfad: list[str] = []

    def besuche(n: str) -> list[str] | None:
        farbe[n] = GRAU
        pfad.append(n)
        for m in kanten[n]:
            if farbe[m] == GRAU:
                return pfad[pfad.index(m):] + [m]
            if farbe[m] == WEISS:
                gefunden = besuche(m)
                if gefunden is not None:
                    return gefunden
        farbe[n] = SCHWARZ
        pfad.pop()
        return None

    for n in formeln:
        if farbe[n] == WEISS:
            zyklus = besuche(n)
            if zyklus is not None:
                return zyklus
    return []


def pruefe_bundle(bundle: RezeptBundle, stand: KatalogStand) -> BundleBericht:
    """Validate a bundle against the active catalog. Pure; no I/O."""
    fehler: list[str] = []
    aktualisierungen: list[str] = []

    # Bundle-defined variables (incl. FORMEL variables derived from the bundle's Formeln).
    bundle_var_gruppen: dict[str, set[VariablenGruppe]] = defaultdict(set)
    bundle_produzierbar: set[str] = set()
    for bv in bundle.variablen:
        name = bv.definition.name
        bundle_var_gruppen[name].add(bv.gruppe)
        if _ist_produzierbar(bv.gruppe, bv.definition):
            bundle_produzierbar.add(name)
    for f in bundle.formeln:
        bundle_var_gruppen[f.name].add(VariablenGruppe.FORMEL)
        bundle_produzierbar.add(f.name)

    known_vars = stand.known_var_namen | set(bundle_var_gruppen)
    produzierbar = stand.produzierbare_namen | bundle_produzierbar
    alle_formeln = {**stand.formeln, **{f.name: f for f in bundle.formeln}}

    # Rule 1 — every bundle Formel parses and references only known variables.
    for f in bundle.formeln:
        for problem in f.validieren(known_vars):
            fehler.append(f"Formel '{f.name}': {problem}")

    # Rule 2 — the formula dependency graph is acyclic.
    zyklus = _hat_zyklus(alle_formeln)
    if zyklus:
        fehler.append("Formelzyklus: " + " -> ".join(zyklus))

    # Rule 3 — every Vorgang cost variable is producible.
    for v in bundle.vorgaenge:
        for kostenart, varname in v.kostenvariablen.items():
            if varname not in produzierbar:
                fehler.append(
                    f"Vorgang '{v.code}': Kostenvariable '{varname}' ({kostenart.value}) ist nicht "
                    f"produzierbar (kein FORMEL/KONSTANTE/STAMMDATEN-Schritt, keine kontext-Variable)."
                )

    # Rule 4 — every code reference resolves (active ∪ bundle).
    aa_codes = stand.ausfuehrungsart_codes | {a.code for a in bundle.ausfuehrungsarten}
    ba_codes = stand.betriebsart_codes | {b.code for b in bundle.betriebsarten}
    kat_codes = stand.betriebskategorie_codes | {k.code for k in bundle.betriebskategorien}
    vg_codes = stand.vorgang_codes | {v.code for v in bundle.vorgaenge}
    leistung_codes = stand.leistung_codes | {lg.code for lg in bundle.leistungen}
    bv_codes = stand.bauverfahren_codes | {b.code for b in bundle.bauverfahren}
    for v in bundle.vorgaenge:
        if v.ausfuehrungsart_code and v.ausfuehrungsart_code not in aa_codes:
            fehler.append(f"Vorgang '{v.code}': unbekannte Ausführungsart '{v.ausfuehrungsart_code}'.")
        if v.betriebsart_code and v.betriebsart_code not in ba_codes:
            fehler.append(f"Vorgang '{v.code}': unbekannte Betriebsart '{v.betriebsart_code}'.")
    for b in bundle.betriebsarten:
        if b.kategorie_code not in kat_codes:
            fehler.append(f"Betriebsart '{b.code}': unbekannte Kategorie '{b.kategorie_code}'.")
    for m in bundle.maschinen:
        if m.ausfuehrungsart_code not in aa_codes:
            fehler.append(f"Maschine '{m.code}': unbekannte Ausführungsart '{m.ausfuehrungsart_code}'.")
    for b in bundle.bauverfahren:
        for vc in b.vorgang_codes:
            if vc not in vg_codes:
                fehler.append(f"Bauverfahren '{b.code}': unbekannter Vorgang '{vc}'.")
    for lk, bcs in bundle.leistung_bauverfahren.items():
        if lk not in leistung_codes:
            fehler.append(f"Mapping: unbekannte Leistung '{lk}'.")
        for bc in bcs:
            if bc not in bv_codes:
                fehler.append(f"Mapping '{lk}': unbekanntes Bauverfahren '{bc}'.")

    # Rule 5 — a bundle variable must not newly shadow an active variable of a different gruppe.
    for name, gruppen in bundle_var_gruppen.items():
        fremd = stand.var_gruppen.get(name, set()) - gruppen
        if fremd:
            gruppen_txt = ", ".join(sorted(g.value for g in fremd))
            fehler.append(
                f"Variable '{name}' kollidiert mit aktiver Gruppe(n) [{gruppen_txt}] — "
                f"der KATALOG-Merge würde die Kollision still auflösen."
            )

    # Rule 6 — bundle keys equal to active keys are supersedes (updates), not errors.
    def flag(codes: set[str], aktiv: set[str], label: str) -> None:
        for code in sorted(codes & aktiv):
            aktualisierungen.append(f"{label} '{code}' aktualisiert eine aktive Version.")

    flag({lg.code for lg in bundle.leistungen}, stand.leistung_codes, "Leistung")
    flag({b.code for b in bundle.bauverfahren}, stand.bauverfahren_codes, "Bauverfahren")
    flag({v.code for v in bundle.vorgaenge}, stand.vorgang_codes, "Vorgang")
    flag({a.code for a in bundle.ausfuehrungsarten}, stand.ausfuehrungsart_codes, "Ausführungsart")
    flag({b.code for b in bundle.betriebsarten}, stand.betriebsart_codes, "Betriebsart")
    flag({k.code for k in bundle.betriebskategorien}, stand.betriebskategorie_codes, "Betriebskategorie")
    flag({f.name for f in bundle.formeln}, set(stand.formeln), "Formel")
    flag({b.code for b in bundle.baustoffe}, stand.baustoff_codes, "Baustoff")
    flag({m.code for m in bundle.maschinen}, stand.maschinen_codes, "Maschine")
    flag(set(bundle.leistung_bauverfahren), stand.leistung_codes, "Mapping")
    for name, gruppen in bundle_var_gruppen.items():
        if gruppen & stand.var_gruppen.get(name, set()):
            aktualisierungen.append(f"Variable '{name}' aktualisiert eine aktive Version.")

    return BundleBericht(fehler=fehler, aktualisierungen=aktualisierungen)
