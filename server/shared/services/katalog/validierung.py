"""Bundle validation (§7) — pure rules over the active catalog + the bundle's own keys.

`lade_stand` reads the active catalog into a `KatalogStand` (the only I/O); `pruefe_bundle` is a
pure function of (bundle, stand) returning a `BundleBericht`. The rules:

1. every bundle Formel parses, is closed over its declared parameter signature, and carries
   prose (beschreibung on the formula and on every parameter — the retrieval corpus must not
   rot back to empty);
2. every Vorgang rechnung is evaluable: known base formulas, every non-default parameter bound,
   binding paths resolve (kontext./stammdaten. variables known AND producible, formel.<instanz>
   defined on the Vorgang, baustoff.<feld> addressable, literals numeric), the instanz graph is
   acyclic, and leistung_instanz names an existing instanz;
3. (retired — formula-level dependency cycles are impossible: base formulas reference only their
   own parameters);
4. every code reference resolves (Ausführungsart/Betriebsart/Kategorie/Vorgang/Leistung/Bauverfahren);
5. a bundle variable does not introduce a new cross-gruppe shadowing — updating an existing
   (name, gruppe) pairing is allowed; only a new pairing creates a collision the KATALOG merge
   would resolve silently;
6. a bundle key equal to an active key is reported as a supersede (an update, not an error);
7./8. prices reference known parties and carry an ordered validity + a positive rate;
9. an `aendere_*` delta only touches registry payload columns (`pruefe_aenderungsfelder`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from shared.models.katalog import (
    BundleBericht,
    BundleVorgang,
    KatalogBundle,
    KatalogEntitaet,
    VariablenGruppe,
)
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository
from shared.services.kalkulation_v2 import einheiten
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    BAUSTOFF_PFAD_EINHEITEN,
    Formel,
    VariableDefinition,
)
from shared.services.katalog.ontologie import basis_kanonformen, isomorphe_basis

# Resolution methods that let the Kalkulator produce a value deterministically (no StateGraph).
_PRODUZIERENDE_METHODEN = {
    AufloesungsMethode.KONSTANTE,
    AufloesungsMethode.STAMMDATEN,
}


@dataclass
class KatalogStand:
    """A snapshot of the active catalog, sufficient to validate a bundle without further I/O."""

    known_var_namen: set[str] = field(default_factory=set)
    produzierbare_namen: set[str] = field(default_factory=set)
    var_gruppen: dict[str, set[VariablenGruppe]] = field(default_factory=lambda: defaultdict(set))
    var_einheiten: dict[str, str | None] = field(default_factory=dict)
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
    lieferanten_codes: set[str] = field(default_factory=set)


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
        stand.var_einheiten[name] = definition.einheit
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
    stand.lieferanten_codes = await codes(KatalogEntitaet.LIEFERANTEN)
    return stand


def _ist_literal(pfad: str) -> bool:
    try:
        Decimal(pfad)
        return True
    except InvalidOperation:
        return False


def _instanz_zyklus(v: BundleVorgang) -> list[str]:
    """Return one cycle of instanz names within the Vorgang's rechnung, else []."""
    kanten: dict[str, set[str]] = {}
    for name, inst in v.rechnung.instanzen.items():
        refs = set()
        for pfad in inst.bindung.values():
            praefix, _, rest = pfad.partition(".")
            if praefix == "formel" and rest in v.rechnung.instanzen:
                refs.add(rest)
        kanten[name] = refs

    WEISS, GRAU, SCHWARZ = 0, 1, 2
    farbe = dict.fromkeys(kanten, WEISS)
    pfad_liste: list[str] = []

    def besuche(n: str) -> list[str] | None:
        farbe[n] = GRAU
        pfad_liste.append(n)
        for m in kanten[n]:
            if farbe[m] == GRAU:
                return pfad_liste[pfad_liste.index(m):] + [m]
            if farbe[m] == WEISS:
                gefunden = besuche(m)
                if gefunden is not None:
                    return gefunden
        farbe[n] = SCHWARZ
        pfad_liste.pop()
        return None

    for n in kanten:
        if farbe[n] == WEISS:
            zyklus = besuche(n)
            if zyklus is not None:
                return zyklus
    return []


def _quell_einheit(
    pfad: str, instanzen: dict, formeln: dict[str, Formel], var_einheiten: dict[str, str | None]
) -> str | None:
    """The einheit a binding source carries, or None when it is unit-free / unknown (a literal, or a
    variable/field without a declared einheit) — such sources are not unit-checked."""
    praefix, _, rest = pfad.partition(".")
    if praefix in ("kontext", "stammdaten") and rest:
        return var_einheiten.get(rest)
    if praefix == "baustoff" and rest:
        return BAUSTOFF_PFAD_EINHEITEN.get(rest)
    if praefix == "formel" and rest and rest in instanzen:
        inst = instanzen[rest]
        formel = formeln.get(inst.formel)
        return inst.ergebnis_einheit or (formel.einheit if formel else None)
    return None


def _pruefe_rechnung(
    v: BundleVorgang,
    formeln: dict[str, Formel],
    known_vars: set[str],
    produzierbar: set[str],
    var_einheiten: dict[str, str | None],
) -> list[str]:
    """Rule 2 — the Vorgang's rechnung is evaluable (see module docstring)."""
    fehler: list[str] = []
    instanzen = v.rechnung.instanzen

    if v.leistung_instanz and v.leistung_instanz not in instanzen:
        fehler.append(
            f"Vorgang '{v.code}': leistung_instanz '{v.leistung_instanz}' ist keine Instanz."
        )

    alle: list[tuple[str, object]] = list(instanzen.items())
    for kostenart, liste in v.rechnung.kosten.items():
        alle.extend((f"{kostenart.value}[{i}]", inst) for i, inst in enumerate(liste))

    for label, inst in alle:
        stelle = f"Vorgang '{v.code}', Instanz '{label}'"
        formel = formeln.get(inst.formel)
        if formel is None:
            fehler.append(f"{stelle}: unbekannte Basisformel '{inst.formel}'.")
            continue
        params = formel.parameter_namen()
        for p in set(inst.bindung) - params:
            fehler.append(f"{stelle}: Bindung für undeklarierten Parameter '{p}'.")
        for p in set(inst.einheiten) - params:
            fehler.append(f"{stelle}: Einheiten-Angabe für undeklarierten Parameter '{p}'.")
        for param in formel.parameter:
            if param.name not in inst.bindung and param.standard is None:
                fehler.append(
                    f"{stelle}: Parameter '{param.name}' ist ungebunden und hat keinen Standard."
                )
        for param_name, pfad in inst.bindung.items():
            praefix, _, rest = pfad.partition(".")
            if praefix in ("kontext", "stammdaten") and rest:
                if rest not in known_vars:
                    fehler.append(f"{stelle}: unbekannte Variable '{pfad}'.")
                elif rest not in produzierbar:
                    fehler.append(
                        f"{stelle}: Variable '{pfad}' ist nicht produzierbar "
                        f"(kein KONSTANTE/STAMMDATEN-Schritt, keine kontext-Variable)."
                    )
            elif praefix == "formel" and rest:
                if rest not in instanzen:
                    fehler.append(f"{stelle}: unbekannte Instanz-Referenz '{pfad}'.")
            elif praefix == "baustoff" and rest:
                if rest not in BAUSTOFF_PFAD_EINHEITEN:
                    adressierbar = ", ".join(sorted(BAUSTOFF_PFAD_EINHEITEN))
                    fehler.append(
                        f"{stelle}: Baustoff-Feld '{rest}' nicht adressierbar — "
                        f"verfügbar: {adressierbar}."
                    )
            elif not _ist_literal(pfad):
                fehler.append(f"{stelle}: unbekannter Bindungspfad '{pfad}'.")

            # Einheit compatibility (§2.5): a bound source's einheit must be dimension-compatible
            # with the parameter's canonical einheit — the converter scales cm→m but never m³→t (a
            # dimension change is a Mengengerüst formula, not a binding). A polymorphic parameter
            # (einheit None) is pinned via `einheiten`; either side unit-free skips the check.
            param = formel.parameter_von(param_name)
            ziel = inst.einheiten.get(param_name) or (param.einheit if param else None)
            quelle = _quell_einheit(pfad, instanzen, formeln, var_einheiten)
            try:
                einheiten.faktor(quelle, ziel)
            except ValueError:
                fehler.append(
                    f"{stelle}: Einheit '{quelle}' der Quelle '{pfad}' passt nicht zum Parameter "
                    f"'{param_name}' ({ziel}) — Dimensionswechsel braucht eine Mengengerüst-Formel, "
                    f"keine Bindung."
                )

    zyklus = _instanz_zyklus(v)
    if zyklus:
        fehler.append(f"Vorgang '{v.code}': Instanz-Zyklus: " + " -> ".join(zyklus))
    return fehler


def pruefe_bundle(bundle: KatalogBundle, stand: KatalogStand) -> BundleBericht:
    """Validate a bundle against the active catalog. Pure; no I/O."""
    fehler: list[str] = []
    aktualisierungen: list[str] = []

    bundle_var_gruppen: dict[str, set[VariablenGruppe]] = defaultdict(set)
    bundle_produzierbar: set[str] = set()
    for bv in bundle.variablen:
        name = bv.definition.name
        bundle_var_gruppen[name].add(bv.gruppe)
        if _ist_produzierbar(bv.gruppe, bv.definition):
            bundle_produzierbar.add(name)

    known_vars = stand.known_var_namen | set(bundle_var_gruppen)
    produzierbar = stand.produzierbare_namen | bundle_produzierbar
    var_einheiten = {**stand.var_einheiten, **{bv.definition.name: bv.definition.einheit for bv in bundle.variablen}}
    alle_formeln = {**stand.formeln, **{f.name: f for f in bundle.formeln}}
    # Structural dedup baseline: the active base formulas' canonical shapes (a bundle formula that
    # UPDATES an active one is excluded — an author may edit F_X itself).
    basis_formen = basis_kanonformen(
        {n: f for n, f in stand.formeln.items() if n not in {b.name for b in bundle.formeln}}
    )

    # Rule 1 — every bundle Formel parses, closes over its signature, carries prose, AND is not a
    # structural re-invention of an existing base formula (§4 dedup — instantiate, don't mint).
    for f in bundle.formeln:
        for problem in f.validieren():
            fehler.append(f"Formel '{f.name}': {problem}")
        if not (f.beschreibung or "").strip():
            fehler.append(
                f"Formel '{f.name}': beschreibung fehlt — ohne Prosa findet der Compiler "
                f"die Formel nicht wieder."
            )
        for param in f.parameter:
            if not (param.beschreibung or "").strip():
                fehler.append(
                    f"Formel '{f.name}': Parameter '{param.name}' ohne beschreibung "
                    f"(Bedeutung + Fundort gehören zur Signatur)."
                )
        isomorph = isomorphe_basis(f.ausdruck, basis_formen)
        if isomorph:
            fehler.append(
                f"Formel '{f.name}': strukturell identisch zu {' / '.join(isomorph)} — "
                f"instanziieren statt neu münzen (nur die Bindung/Einheiten unterscheiden sich)."
            )

    # Rule 1b — every bundle Variable carries retrieval-grade prose (§2.6). The corpus cannot rot
    # back to empty beschreibungen: the compiler retrieves over this prose to find an existing
    # variable instead of minting one.
    for bv in bundle.variablen:
        if not (bv.definition.beschreibung or "").strip():
            fehler.append(
                f"Variable '{bv.definition.name}': beschreibung fehlt — ohne Prosa "
                f"(Bedeutung, welchen Parameter sie speist, Fundort) findet der Compiler sie "
                f"nicht wieder."
            )

    # Rule 2 — every Vorgang rechnung is evaluable.
    for v in bundle.vorgaenge:
        fehler.extend(_pruefe_rechnung(v, alle_formeln, known_vars, produzierbar, var_einheiten))

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

    # Rule 7/8 — a bundle price references a known Lieferant AND Baustoff (active ∪ bundle), and
    # carries an ordered validity + a positive rate.
    lieferant_codes = stand.lieferanten_codes | {lf.code for lf in bundle.lieferanten}
    baustoff_codes = stand.baustoff_codes | {bst.code for bst in bundle.baustoffe}
    for p in bundle.preise:
        stelle = f"Preis {p.lieferant_code}/{p.baustoff_code}"
        if p.lieferant_code not in lieferant_codes:
            fehler.append(f"{stelle}: unbekannter Lieferant '{p.lieferant_code}'.")
        if p.baustoff_code not in baustoff_codes:
            fehler.append(f"{stelle}: unbekannter Baustoff '{p.baustoff_code}'.")
        if p.gueltig_bis is not None and p.gueltig_ab > p.gueltig_bis:
            fehler.append(f"{stelle}: gueltig_ab {p.gueltig_ab} liegt nach gueltig_bis {p.gueltig_bis}.")
        if p.preis_eur_pro_t <= 0:
            fehler.append(f"{stelle}: preis_eur_pro_t muss > 0 sein (ist {p.preis_eur_pro_t}).")

    # Rule 5 — a bundle variable must not introduce a NEW cross-gruppe shadowing. Updating an
    # existing (name, gruppe) pairing is allowed even when the name is deliberately shadowed
    # already; only a pairing the active catalog does not have yet creates a collision the
    # KATALOG merge would resolve silently.
    for name, gruppen in bundle_var_gruppen.items():
        aktive_gruppen = stand.var_gruppen.get(name, set())
        alle = aktive_gruppen | gruppen
        if (gruppen - aktive_gruppen) and len(alle) > 1:
            gruppen_txt = ", ".join(sorted(g.value for g in alle))
            fehler.append(
                f"Variable '{name}': neue Gruppen-Kollision [{gruppen_txt}] — "
                f"der KATALOG-Merge würde sie still auflösen."
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
    flag({lf.code for lf in bundle.lieferanten}, stand.lieferanten_codes, "Lieferant")
    flag(set(bundle.leistung_bauverfahren), stand.leistung_codes, "Mapping")
    for name, gruppen in bundle_var_gruppen.items():
        if gruppen & stand.var_gruppen.get(name, set()):
            aktualisierungen.append(f"Variable '{name}' aktualisiert eine aktive Version.")

    return BundleBericht(fehler=fehler, aktualisierungen=aktualisierungen)


def pruefe_aenderungsfelder(
    entitaet: KatalogEntitaet, aenderungen: dict[str, object]
) -> list[str]:
    """Rule 9 — an `aendere_*` delta may only touch the entity's registry payload columns. Returns
    one error per unknown field, naming the valid ones (empty list when the delta is clean). The
    registry payload is the single source of truth for what an entity's editable fields are."""
    erlaubt = set(KATALOG_REGISTRY[entitaet].payload)
    valid = ", ".join(sorted(erlaubt))
    return [
        f"unbekanntes Feld '{feld}' für {entitaet.value} — erlaubt: {valid}."
        for feld in aenderungen
        if feld not in erlaubt
    ]
