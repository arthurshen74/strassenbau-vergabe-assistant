"""The katalog_chat agent's recipe-compiler tool — W18 `rezept_entwurf_speichern` (Phase 3, D1).

The compiler is the agent plus this ONE tool: the agent discovers with the T-tools, then emits the
full recipe as a `KatalogBundle` transport dict plus a justification envelope — `wiederverwendung`
(every existing entity the recipe binds, justified) and `neu` (every minted code, justified why
nothing existing fits). The tool

1. normalises the transport dict into a `KatalogBundle` (variables arrive in the simplified W10/W12
   shape and get their cascade built server-side; a Vorgang carries its `rechnung` of base-formula
   instantiations; a minted Formel is a base formula with a declared parameter signature),
2. validates with the full store rule set via `KatalogEntwurfDienst.pruefen` — nothing weakened,
3. checks the justification lists for coverage (every code defined or referenced by the bundle —
   including each instantiated base formula and each bound variable — appears in exactly one list),
4. BM25-probes every minted Vorgang/Ausführungsart/Betriebsart/Stammdaten-Variable against the
   active catalog and warns on a near-duplicate (soft reuse pressure, §4 — warnings never block),
5. persists the drafts sharing one bundle_uuid on success; on any error nothing persists and the
   report returns for agentic repair.

The envelope is the confirm card's content AND the eval's measurement surface (reuse rate reads
`wiederverwendung`/`neu` directly). Activation stays human-only on the card (D8 boundary).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBauverfahren,
    BundleLieferant,
    BundlePreis,
    BundleVariable,
    BundleVorgang,
    KatalogBundle,
    VariablenGruppe,
)
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    AufloesungsSchritt,
    Ausführungsart,
    Baustoff,
    Betriebsart,
    Betriebskategorie,
    D,
    Datentyp,
    Formel,
    Kostenart,
    Leistung,
    Maschine,
    VariableDefinition,
)
from shared.services.kalkulation_v2.store import GEOM
from shared.services.katalog.entwurf_dienst import DEFAULT_AUTOR, KatalogEntwurfDienst
from shared.services.katalog.werkzeuge_schreiben import _formel_latex, _normalisieren

# BM25 score at/above which an active-catalog hit counts as a near-duplicate of a minted entity.
# Calibrated on the seeded catalog: one matching domain token ("fräsen") scores ~3.9; generic-token
# noise ("je", "aufnehmen") stays <= 3.3.
DUBLETTEN_SCHWELLE = 3.5

_KOSTENARTEN = {k.value.lower(): k.value for k in Kostenart}

# The binding-path prefixes that name a catalog variable (vs. baustoff fields, sibling instanzen,
# or literals) — mirrors einheiten/model binding grammar. Used by coverage + the geometry walk.
_VAR_PRAEFIXE = ("kontext", "stammdaten")


def _vorgang_normalisieren(v: dict[str, Any]) -> dict[str, Any]:
    """Case-insensitive Kostenart keys inside `rechnung.kosten` ("lohn" → "Lohn"); unknown keys
    pass through so the Pydantic error names them. Non-dict rechnung passes through untouched."""
    rechnung = v.get("rechnung")
    if not isinstance(rechnung, dict) or not isinstance(rechnung.get("kosten"), dict):
        return v
    kosten = {_KOSTENARTEN.get(str(k).lower(), k): val for k, val in rechnung["kosten"].items()}
    return {**v, "rechnung": {**rechnung, "kosten": kosten}}


def _instanz_bindungen(inst: Any) -> dict[str, str]:
    """The bindung dict of a FormelInstanz whether it arrived as a model or a raw dict."""
    if isinstance(inst, dict):
        return inst.get("bindung") or {}
    return inst.bindung


def _vorgang_instanzen(v: Any):
    """Every FormelInstanz in a (bundle or payload) Vorgang's Rechnung — named + cost lines."""
    rechnung = v.get("rechnung") if isinstance(v, dict) else v.rechnung
    if rechnung is None:
        return
    instanzen = rechnung.get("instanzen") if isinstance(rechnung, dict) else rechnung.instanzen
    kosten = rechnung.get("kosten") if isinstance(rechnung, dict) else rechnung.kosten
    yield from (instanzen or {}).values()
    for liste in (kosten or {}).values():
        yield from liste


def _instanz_formel(inst: Any) -> str | None:
    return inst.get("formel") if isinstance(inst, dict) else inst.formel


def _gebundene_variablen(v: Any) -> set[str]:
    """The kontext./stammdaten. variables a Vorgang's Rechnung binds (across all instanzen)."""
    return {
        rest
        for inst in _vorgang_instanzen(v)
        for pfad in _instanz_bindungen(inst).values()
        for praefix, _, rest in [str(pfad).partition(".")]
        if praefix in _VAR_PRAEFIXE and rest
    }


def _gebundene_geometrie(v: Any) -> set[str]:
    """The kontext-geometry variables a Vorgang's Rechnung binds (a subset of GEOM values)."""
    geom = set(GEOM.values())
    return {
        rest
        for inst in _vorgang_instanzen(v)
        for pfad in _instanz_bindungen(inst).values()
        for praefix, _, rest in [str(pfad).partition(".")]
        if praefix == "kontext" and rest in geom
    }


def _variable_bauen(roh: dict[str, Any]) -> BundleVariable:
    """Build a BundleVariable from the simplified transport shape (the W10/W12 server-side cascade):
    stammdaten = one KONSTANTE step from `wert`; kontext = optional LANGTEXT+RAG from `llm_hinweis`,
    then HITL, then an optional KONSTANTE fallback from `default_wert`."""
    gruppe = VariablenGruppe(str(roh["gruppe"]).lower())
    name, bezeichnung = roh["name"], roh["bezeichnung"]
    einheit = roh.get("einheit")
    schritte: list[AufloesungsSchritt] = []
    if gruppe == VariablenGruppe.STAMMDATEN:
        if roh.get("wert") is None:
            raise ValueError(f"Variable '{name}': stammdaten-Variable braucht einen `wert`.")
        schritte = [AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=D(roh["wert"]))]
    elif gruppe == VariablenGruppe.KONTEXT:
        if roh.get("llm_hinweis"):
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.LANGTEXT,
                prompt=f"Aus LV-Langtext/Hinweisen: {bezeichnung} ({einheit or '-'}).",
                konfidenz_schwelle=D("0.75"),
            ))
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.RAG, prompt=roh["llm_hinweis"], konfidenz_schwelle=D("0.60")
            ))
        schritte.append(AufloesungsSchritt(methode=AufloesungsMethode.HITL))
        if roh.get("default_wert") is not None:
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.KONSTANTE, konstante=D(roh["default_wert"])
            ))
    else:
        raise ValueError(
            f"Variable '{name}': gruppe muss stammdaten oder kontext sein "
            "(formel-Variablen entstehen automatisch aus den Formeln)."
        )
    definition = VariableDefinition(
        name=name, bezeichnung=bezeichnung, beschreibung=roh.get("beschreibung"), einheit=einheit,
        datentyp=Datentyp(str(roh["datentyp"]).lower()) if roh.get("datentyp") else Datentyp.DEZIMAL,
        llm_kontext=roh.get("llm_hinweis"), aufloesung=schritte,
    )
    return BundleVariable(gruppe=gruppe, definition=definition)


def bundle_bauen(roh: dict[str, Any]) -> tuple[KatalogBundle | None, list[str]]:
    """Normalise the transport dict into a KatalogBundle. Collects ALL section errors instead of
    stopping at the first, so the agent repairs everything in one round."""
    fehler: list[str] = []

    def sektion(feld: str, bauen) -> list:
        ergebnisse = []
        for i, eintrag in enumerate(roh.get(feld) or []):
            try:
                ergebnisse.append(bauen(eintrag))
            except KeyError as e:
                kennung = eintrag.get("code") or eintrag.get("name") if isinstance(eintrag, dict) else None
                fehler.append(f"{feld}[{kennung or i}]: fehlendes Feld {e}.")
            except (ValidationError, ValueError, TypeError) as e:
                kennung = eintrag.get("code") or eintrag.get("name") if isinstance(eintrag, dict) else None
                fehler.append(f"{feld}[{kennung or i}]: {e}")
        return ergebnisse

    leistungen = sektion("leistungen", Leistung.model_validate)
    bauverfahren = sektion("bauverfahren", BundleBauverfahren.model_validate)
    vorgaenge = sektion("vorgaenge", lambda v: BundleVorgang.model_validate(_vorgang_normalisieren(v)))
    ausfuehrungsarten = sektion("ausfuehrungsarten", Ausführungsart.model_validate)
    betriebskategorien = sektion("betriebskategorien", Betriebskategorie.model_validate)
    betriebsarten = sektion("betriebsarten", Betriebsart.model_validate)
    formeln = sektion("formeln", Formel.model_validate)
    variablen = sektion("variablen", _variable_bauen)
    baustoffe = sektion("baustoffe", Baustoff.model_validate)
    maschinen = sektion("maschinen", Maschine.model_validate)
    lieferanten = sektion("lieferanten", BundleLieferant.model_validate)
    preise = sektion("preise", lambda p: BundlePreis.model_validate(
        {**p, "gueltig_ab": p.get("gueltig_ab") or date.today().isoformat()}
    ))

    mapping = roh.get("leistung_bauverfahren") or {}
    if not isinstance(mapping, dict):
        fehler.append("leistung_bauverfahren: erwartet {leistung_code: [bauverfahren_codes]}.")
        mapping = {}

    if fehler:
        return None, fehler
    bundle = KatalogBundle(
        leistungen=leistungen, bauverfahren=bauverfahren, vorgaenge=vorgaenge,
        ausfuehrungsarten=ausfuehrungsarten, betriebskategorien=betriebskategorien,
        betriebsarten=betriebsarten, formeln=formeln, variablen=variablen,
        baustoffe=baustoffe, maschinen=maschinen, lieferanten=lieferanten, preise=preise,
        leistung_bauverfahren=mapping,
    )
    if not any(getattr(bundle, feld) for feld in KatalogBundle.model_fields):
        return None, ["leerer Bundle — keine Entität übergeben."]
    return bundle, []


# --------------------------------------------------------------------------- #
# Justification coverage (§3) — mechanical, not LLM trust.
# --------------------------------------------------------------------------- #
def _definierte_codes(bundle: KatalogBundle) -> set[str]:
    return (
        {lg.code for lg in bundle.leistungen}
        | {b.code for b in bundle.bauverfahren}
        | {v.code for v in bundle.vorgaenge}
        | {a.code for a in bundle.ausfuehrungsarten}
        | {k.code for k in bundle.betriebskategorien}
        | {b.code for b in bundle.betriebsarten}
        | {f.name for f in bundle.formeln}
        | {bv.definition.name for bv in bundle.variablen}
        | {b.code for b in bundle.baustoffe}
        | {m.code for m in bundle.maschinen}
        | {lf.code for lf in bundle.lieferanten}
    )


def _referenzierte_codes(bundle: KatalogBundle) -> set[str]:
    """Every EXISTING code/name a bundle entity binds and must justify: taxonomy references, chain
    members, mapping entries, price parties, and — per Vorgang Rechnung — each instantiated base
    formula plus each kontext./stammdaten. variable and machine-override rate key. Base formulas
    reference only their own local parameters, so a minted formula adds no external references;
    `formel.<instanz>` binding paths are internal (sibling instanzen), not codes."""
    codes: set[str] = set()
    for v in bundle.vorgaenge:
        codes.update(c for c in (v.ausfuehrungsart_code, v.betriebsart_code) if c)
        codes.update(v.kosten_bindung)
        codes.update(_gebundene_variablen(v))
        codes.update(fn for inst in _vorgang_instanzen(v) if (fn := _instanz_formel(inst)))
    for b in bundle.betriebsarten:
        codes.add(b.kategorie_code)
    for m in bundle.maschinen:
        codes.add(m.ausfuehrungsart_code)
        codes.update(p.betriebsart_code for p in m.leistungsprofile)
    for b in bundle.bauverfahren:
        codes.update(b.vorgang_codes)
    for lk, bcs in bundle.leistung_bauverfahren.items():
        codes.add(lk)
        codes.update(bcs)
    for p in bundle.preise:
        codes.update((p.lieferant_code, p.baustoff_code))
    return codes


def pruefe_abdeckung(
    bundle: KatalogBundle,
    wiederverwendung: list[dict[str, str]],
    neu: list[dict[str, str]],
) -> list[str]:
    """Coverage of the justification lists: every code the bundle defines or references appears in
    exactly one of the two lists; `neu` may only name codes the bundle itself defines."""
    fehler: list[str] = []
    for feld, liste in (("wiederverwendung", wiederverwendung), ("neu", neu)):
        for i, eintrag in enumerate(liste):
            if not isinstance(eintrag, dict) or not eintrag.get("code"):
                fehler.append(f"{feld}[{i}]: Eintrag braucht einen `code`.")
    if fehler:
        return fehler

    definiert = _definierte_codes(bundle)
    referenziert = _referenzierte_codes(bundle) - definiert
    alle = definiert | referenziert
    genannt_w = {e["code"] for e in wiederverwendung}
    genannt_n = {e["code"] for e in neu}

    for code in sorted(genannt_w & genannt_n):
        fehler.append(f"Abdeckung: '{code}' steht in beiden Listen (wiederverwendung UND neu).")
    for code in sorted(alle - genannt_w - genannt_n):
        fehler.append(
            f"Abdeckung: '{code}' wird im Bundle "
            f"{'definiert' if code in definiert else 'referenziert'}, ist aber nicht begründet "
            "(in wiederverwendung oder neu aufführen)."
        )
    for code in sorted((genannt_w | genannt_n) - alle):
        fehler.append(f"Abdeckung: '{code}' ist begründet, kommt im Bundle aber nicht vor.")
    for code in sorted(genannt_n - definiert):
        if code in alle:
            fehler.append(
                f"Abdeckung: '{code}' steht in neu, wird im Bundle aber nur referenziert — "
                "eine Referenz auf Bestehendes gehört in wiederverwendung."
            )
    return fehler


async def geometrie_warnungen(dienst: KatalogEntwurfDienst, bundle: KatalogBundle) -> list[str]:
    """A recipe whose Rechnung binds a geometry variable other than the billed one (the Leistung's
    GEOM[einheit]) validates but is not deterministically calculable: only the billed unit's
    variable is booked from the menge. The trap hides in REUSED chain members (an m²-based Vorgang
    in a t-billed recipe). Warn, never block: the calculator graph can still resolve the foreign
    geometry via HITL. All Instanzen of a Vorgang live in one Rechnung, so scanning their kontext
    bindings catches the transitive case without a formula graph walk."""
    gebucht = {
        GEOM[lg.einheit] for lg in bundle.leistungen if lg.einheit and lg.einheit in GEOM
    }
    if not gebucht:
        return []

    _, aktive_vorgaenge = await dienst.aktive_formeln_und_vorgaenge()

    # Every Vorgang in the recipe's chains — the bundle's own AND reused active chain members.
    stellen: dict[str, Any] = {f"Vorgang '{v.code}'": v for v in bundle.vorgaenge}
    bundle_vorgang_codes = {v.code for v in bundle.vorgaenge}
    for b in bundle.bauverfahren:
        for code in b.vorgang_codes:
            if code in bundle_vorgang_codes:
                continue
            p = aktive_vorgaenge.get(code)
            if p is not None:
                stellen[f"wiederverwendeter Vorgang '{code}'"] = p

    warnungen: list[str] = []
    for stelle, v in stellen.items():
        for var in sorted(_gebundene_geometrie(v) - gebucht):
            warnungen.append(
                f"Geometrie: {stelle} bindet '{var}', gebucht wird aber "
                f"{'/'.join(sorted(gebucht))} — '{var}' ist bei der Kalkulation nicht gefüllt "
                "(nur per Rückfrage auflösbar). Direkt von der gebuchten Größe rechnen."
            )
    return warnungen


# --------------------------------------------------------------------------- #
# Near-duplicate warnings (§4) — soft reuse pressure, never blocking.
# --------------------------------------------------------------------------- #
async def _dubletten_warnungen(dienst: KatalogEntwurfDienst, bundle: KatalogBundle) -> list[str]:
    """BM25-match every minted Vorgang/Ausführungsart/Betriebsart/Stammdaten-Variable against the
    active catalog; a hit at/above DUBLETTEN_SCHWELLE names the existing candidate."""
    sonden: list[tuple[str, str, str, str]] = []  # (entitaet, code, anzeige, suchtext)
    for v in bundle.vorgaenge:
        sonden.append(("vorgaenge", v.code, "Vorgang", v.name))
    for a in bundle.ausfuehrungsarten:
        sonden.append(("ausfuehrungsarten", a.code, "Geräteklasse",
                       " ".join(t for t in (a.name, a.geraetebezug) if t)))
    for b in bundle.betriebsarten:
        sonden.append(("betriebsarten", b.code, "Betriebsart",
                       " ".join(t for t in (b.bezeichnung, b.beschreibung) if t)))
    for bv in bundle.variablen:
        if bv.gruppe == VariablenGruppe.STAMMDATEN:
            sonden.append(("variablen", bv.definition.name, "Stammdaten-Variable",
                           bv.definition.bezeichnung))

    warnungen: list[str] = []
    for entitaet, code, anzeige, suchtext in sonden:
        treffer = await dienst.suche(suchtext, entitaeten=[entitaet], limit=3)
        bester = next((t for t in treffer if t["schluessel"] != code), None)
        if bester is not None and bester["score"] >= DUBLETTEN_SCHWELLE:
            warnungen.append(
                f"Mögliche Dublette: {anzeige} '{code}' ähnelt aktivem Eintrag "
                f"'{bester['schluessel']}' ({bester['name']}, Score {bester['score']}). "
                "Wiederverwendung prüfen."
            )
    return warnungen


# --------------------------------------------------------------------------- #
# The envelope (card content + eval measurement surface)
# --------------------------------------------------------------------------- #
def _entwurf_ansicht(bundle: KatalogBundle) -> dict[str, Any]:
    """The card's sectioned draft view: model dumps per entity; Formeln carry LaTeX + legend;
    Variablen show their cascade methods."""
    ansicht = bundle.model_dump(mode="json", exclude={"formeln", "variablen"}, exclude_defaults=True)
    ansicht["formeln"] = [
        {
            "name": f.name, "ausdruck": f.ausdruck, "einheit": f.einheit,
            "beschreibung": f.beschreibung,
            "parameter": [p.model_dump(mode="json") for p in f.parameter],
            **_formel_latex(f.ausdruck),
        }
        for f in bundle.formeln
    ]
    ansicht["variablen"] = [
        {
            "name": bv.definition.name, "gruppe": bv.gruppe.value,
            "bezeichnung": bv.definition.bezeichnung, "einheit": bv.definition.einheit,
            "kaskade": [s.methode.value for s in bv.definition.aufloesung],
            "wert": next((s.konstante for s in bv.definition.aufloesung
                          if s.methode == AufloesungsMethode.KONSTANTE), None),
        }
        for bv in bundle.variablen
    ]
    return ansicht


def _rezept_huelle(
    *,
    bundle_uuid: str | None,
    schluessel: str,
    fehler: list[str],
    aktualisierungen: list[str] | None = None,
    entwurf: dict[str, Any] | None = None,
    wiederverwendung: list[dict[str, str]] | None = None,
    neu: list[dict[str, str]] | None = None,
    warnungen: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    envelope = _normalisieren(
        {
            "bundle_uuid": bundle_uuid,
            "aktion": "rezept",
            "entitaet": "bundle",
            "schluessel": schluessel,
            "bericht": {"fehler": fehler, "aktualisierungen": aktualisierungen or []},
            "entwurf": entwurf,
            "wiederverwendung": wiederverwendung,
            "neu": neu,
            "warnungen": warnungen,
        }
    )
    return json.dumps(envelope, ensure_ascii=False), envelope


def _schluessel(roh: dict[str, Any], bundle: KatalogBundle | None) -> str:
    """The envelope key: the recipe's Leistung code, else the first defined code."""
    if bundle is not None:
        for eintraege in (bundle.leistungen, bundle.bauverfahren, bundle.vorgaenge):
            if eintraege:
                return eintraege[0].code
        definiert = _definierte_codes(bundle)
        if definiert:
            return sorted(definiert)[0]
    for eintrag in roh.get("leistungen") or []:
        if isinstance(eintrag, dict) and eintrag.get("code"):
            return eintrag["code"]
    return "rezept"


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #
def katalog_rezept_werkzeuge(engine: AsyncEngine) -> list[BaseTool]:
    """Build the W18 recipe-compiler tool bound to `engine`."""
    dienst = KatalogEntwurfDienst(engine)

    @tool(response_format="content_and_artifact")
    async def rezept_entwurf_speichern(
        bundle: dict[str, Any],
        wiederverwendung: list[dict[str, str]],
        neu: list[dict[str, str]],
    ) -> tuple[str, dict[str, Any]]:
        """Ein vollständiges Rezept (Leistung + Bauverfahren + Vorgänge + Formeln + Variablen +
        Mapping, beliebige Teilmenge) als EINEN Entwurfs-Bundle speichern. Erst suchen, dann münzen:
        jede Bindung an Bestehendes gehört nach `wiederverwendung`, jeder neue Code nach `neu` —
        beide Listen werden mechanisch auf Abdeckung geprüft (jeder Code aus dem Bundle in genau
        einer Liste). Nichts wird aktiviert; der Nutzer bestätigt auf der Karte.

        `bundle`-Form (alle Felder optional, nur was das Rezept braucht):
        - leistungen: [{code, name, einheit, beschreibung?, standard_kennung?}]
        - bauverfahren: [{code, name, vorgang_codes: [geordnet, erster zuerst]}]
        - vorgaenge: [{code, name, ausfuehrungsart_code?, betriebsart_code?, leistung_instanz?,
          kosten_bindung?: {stammdaten_satz: maschinen_eigenschaft}, rechnung: {
            instanzen?: {name: INSTANZ},   # benannte Mengen/Kurven, referenzierbar als formel.<name>
            kosten: {Material|Maschine|Antransport|Abtransport|Entsorgung|Lohn: [INSTANZ, ...]}}}]
          INSTANZ = {formel: BASISFORMEL, bindung: {parameter: quelle}, einheiten?: {parameter:
            einheit}, ergebnis_einheit?, variable?: gebuchte_variable, bezeichnung?}. `quelle` ist
            `kontext.<var>` / `stammdaten.<var>` (Kaskaden-Auflösung), `baustoff.<feld>`,
            `formel.<instanz>` (Geschwister-Instanz) oder eine Zahl (Literal). ERST vorhandene
            Basisformeln instanziieren (liste_formeln/zeige_formel), nur bei echt neuer Form münzen.
        - ausfuehrungsarten: [{code, name, geraetebezug?}]  (Geräteklassen)
        - betriebskategorien: [{code, bezeichnung, beschreibung?}]
        - betriebsarten: [{code, bezeichnung, kategorie_code, einheit?, beschreibung?}]
        - formeln: [{name, ausdruck, einheit?, beschreibung, parameter: [{name, einheit?,
          beschreibung, standard?}]}] — eine neue BASISFORMEL über deklarierte Parameter
          (kanonische Einheiten; Umrechnung bei der Bindung). Formeln sind KEINE Variablen mehr.
        - variablen: [{name, gruppe: "stammdaten"|"kontext", bezeichnung, einheit?, wert?,
          llm_hinweis?, default_wert?, beschreibung?}] — Kaskade wird serverseitig gebaut
          (stammdaten braucht `wert`; kontext: llm_hinweis → LV/RAG-Stufen, default_wert → Rückfall)
        - baustoffe: [{code, name, rohdichte_t_pro_m3, verdichtungsfaktor?, kategorie?, koernung?,
          basispreis_eur_pro_t?}]
        - maschinen / lieferanten / preise: wie bei neue_maschine / neuer_lieferant / neuer_preis
        - leistung_bauverfahren: {leistung_code: [bauverfahren_codes]} — das Mapping, sonst ist die
          Leistung nicht kalkulierbar

        `wiederverwendung`: [{code, warum}] — jede gebundene bestehende Entität/Variable.
        `neu`: [{code, warum_nicht_vorhanden}] — jeder gemünzte Code.

        Bei Validierungs- oder Abdeckungsfehlern wird NICHTS gespeichert; `bericht.fehler` nennt
        alle Probleme — korrigieren und erneut aufrufen. Dubletten-Warnungen blockieren nicht."""
        kbundle, bau_fehler = bundle_bauen(bundle)
        schluessel = _schluessel(bundle, kbundle)
        if kbundle is None:
            return _rezept_huelle(
                bundle_uuid=None, schluessel=schluessel, fehler=bau_fehler,
                wiederverwendung=wiederverwendung, neu=neu,
            )

        bericht = await dienst.pruefen(kbundle)
        fehler = bericht.fehler + pruefe_abdeckung(kbundle, wiederverwendung, neu)
        warnungen = await geometrie_warnungen(dienst, kbundle)
        warnungen += await _dubletten_warnungen(dienst, kbundle)
        entwurf = _entwurf_ansicht(kbundle)
        if fehler:
            return _rezept_huelle(
                bundle_uuid=None, schluessel=schluessel, fehler=fehler,
                aktualisierungen=bericht.aktualisierungen, entwurf=entwurf,
                wiederverwendung=wiederverwendung, neu=neu, warnungen=warnungen,
            )
        bundle_uuid = await dienst.entwurf_speichern(kbundle, benutzer=DEFAULT_AUTOR)
        return _rezept_huelle(
            bundle_uuid=str(bundle_uuid), schluessel=schluessel, fehler=[],
            aktualisierungen=bericht.aktualisierungen, entwurf=entwurf,
            wiederverwendung=wiederverwendung, neu=neu, warnungen=warnungen,
        )

    return [rezept_entwurf_speichern]
