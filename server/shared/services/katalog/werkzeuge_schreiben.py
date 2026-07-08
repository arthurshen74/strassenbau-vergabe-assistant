"""The katalog_chat agent's WRITE tool surface — the 17 write tools W1–W17 (Phase 2, §5).

Every write tool is a thin `@tool` wrapper that builds a minimal `KatalogBundle` (or a delta over the
active entity), saves it as a draft through `KatalogEntwurfDienst`, and returns the **draft envelope**
`{bundle_uuid, aktion, entitaet, schluessel, bericht, diff?, entwurf, warnungen?}` as a
`content_and_artifact` pair — JSON for the LLM, the same dict as the artifact the confirm card renders.
A tool NEVER activates: it validates and persists a proposal; activation is a human action on the card
(the boundary is enforced structurally, see `test_katalog_readonly.py`). On a validation failure
nothing is persisted, `bundle_uuid` is absent and `bericht.fehler` explains why; the agent relays it
and may retry with corrected input. `benutzer` is `DEFAULT_AUTOR` until auth lands.

`aendere_*` tools load the active payload server-side, apply only the named fields (Rule 9 whitelist),
and return a server-computed `diff` so the card shows exactly what changes — the LLM never retypes the
untouched fields.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBericht,
    BundleLieferant,
    BundlePreis,
    BundleVariable,
    KatalogBundle,
    KatalogEntitaet,
    VariablenGruppe,
)
from shared.services.kalkulation_v2.formel_darstellung import stelle_formel_dar
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
    FormelParameter,
    Leistungsprofil,
    Maschine,
    MaschinenWert,
    VariableDefinition,
)
from shared.services.katalog.entwurf_dienst import DEFAULT_AUTOR, KatalogEntwurfDienst
from shared.services.katalog.service import BundleNichtGefunden
from shared.services.katalog.validierung import pruefe_aenderungsfelder


# --------------------------------------------------------------------------- #
# Envelope helpers
# --------------------------------------------------------------------------- #
def _normalisieren(obj: Any) -> Any:
    """Normalise an envelope for JSON/LLM consumption: drop None, stringify Decimal/date, unwrap Enum."""
    if isinstance(obj, dict):
        return {k: _normalisieren(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_normalisieren(v) for v in obj]
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _huelle(
    *,
    bundle_uuid: UUID | None,
    aktion: str,
    entitaet: str,
    schluessel: str,
    bericht: BundleBericht,
    entwurf: dict[str, Any] | None = None,
    diff: list[dict[str, Any]] | None = None,
    warnungen: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the draft envelope as a (json, artifact) pair. bundle_uuid absent ⇒ nothing was saved."""
    envelope = _normalisieren(
        {
            "bundle_uuid": str(bundle_uuid) if bundle_uuid is not None else None,
            "aktion": aktion,
            "entitaet": entitaet,
            "schluessel": schluessel,
            "bericht": {"fehler": bericht.fehler, "aktualisierungen": bericht.aktualisierungen},
            "diff": diff,
            "entwurf": entwurf,
            "warnungen": warnungen,
        }
    )
    return json.dumps(envelope, ensure_ascii=False), envelope


def _fehler(
    *, aktion: str, entitaet: str, schluessel: str, meldungen: list[str],
    entwurf: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    return _huelle(
        bundle_uuid=None, aktion=aktion, entitaet=entitaet, schluessel=schluessel,
        bericht=BundleBericht(fehler=meldungen), entwurf=entwurf,
    )


async def _speichern(
    dienst: KatalogEntwurfDienst, bundle: KatalogBundle, *,
    aktion: str, entitaet: str, schluessel: str, entwurf: dict[str, Any],
    diff: list[dict[str, Any]] | None = None, warnungen: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate → save-draft → envelope. On invalid nothing is persisted; the report explains why."""
    bericht = await dienst.pruefen(bundle)
    if not bericht.gueltig:
        return _huelle(
            bundle_uuid=None, aktion=aktion, entitaet=entitaet, schluessel=schluessel,
            bericht=bericht, entwurf=entwurf, diff=diff, warnungen=warnungen,
        )
    bundle_uuid = await dienst.entwurf_speichern(bundle, benutzer=DEFAULT_AUTOR)
    return _huelle(
        bundle_uuid=bundle_uuid, aktion=aktion, entitaet=entitaet, schluessel=schluessel,
        bericht=bericht, entwurf=entwurf, diff=diff, warnungen=warnungen,
    )


def _diff(alt: dict[str, Any], aenderungen: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"feld": k, "alt": alt.get(k), "neu": v} for k, v in aenderungen.items()]


def _formel_latex(ausdruck: str) -> dict[str, Any]:
    """LaTeX + legend for a formula expression, or {} when it does not parse (the validator reports
    the syntax error separately)."""
    try:
        d = stelle_formel_dar(ausdruck)
    except SyntaxError:
        return {}
    return {"latex": d.latex, "legende": [e.model_dump() for e in d.legende]}


def _als_datum(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


# --------------------------------------------------------------------------- #
# The write tools
# --------------------------------------------------------------------------- #
def katalog_schreib_werkzeuge(engine: AsyncEngine) -> list[BaseTool]:
    """Build the 17 write tools bound to `engine`, all routed through one `KatalogEntwurfDienst`."""
    dienst = KatalogEntwurfDienst(engine)

    # --- Formeln & Variablen (batch A, W8–W12) ----------------------------- #
    @tool(response_format="content_and_artifact")
    async def neue_formel(
        name: str, ausdruck: str, beschreibung: str,
        parameter: list[dict[str, Any]], einheit: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue BASISFORMEL als Entwurf anlegen — nur wenn keine vorhandene passt (erst
        liste_formeln/zeige_formel prüfen; die Regel ist instanziieren, nicht münzen). `ausdruck`
        ist ein DSL-Ausdruck über die DEKLARIERTEN Parameter (nur vorhandenes Vokabular; erfinde
        KEINE Funktion — siehe zeige_dsl_funktionen). Jeder im Ausdruck genutzte Name MUSS ein
        deklarierter Parameter sein, und jeder Parameter MUSS im Ausdruck vorkommen. `beschreibung`
        (Formel und jeder Parameter) ist Pflicht — ohne Prosa findet der Compiler die Formel nicht
        wieder. Kanonische Einheiten (m, m², m³, t, h, €, St, l, km); Umrechnung passiert bei der
        Bindung, nicht im Ausdruck. Nichts wird aktiviert — der Nutzer bestätigt auf der Karte.

        `parameter`: [{name, einheit?, beschreibung, standard?}] — die formale Signatur; `standard`
        ist der Rückfallwert, wenn eine Instanz den Parameter ungebunden lässt."""
        formel = Formel(
            name=name, ausdruck=ausdruck, einheit=einheit, beschreibung=beschreibung,
            parameter=[FormelParameter.model_validate(p) for p in parameter],
        )
        entwurf = {
            "name": name, "ausdruck": ausdruck, "einheit": einheit, "beschreibung": beschreibung,
            "parameter": [p.model_dump(mode="json") for p in formel.parameter],
            **_formel_latex(ausdruck),
        }
        return await _speichern(
            dienst, KatalogBundle(formeln=[formel]),
            aktion="neu", entitaet=KatalogEntitaet.FORMELN.value, schluessel=name, entwurf=entwurf,
        )

    @tool(response_format="content_and_artifact")
    async def aendere_formel(
        name: str, ausdruck: str | None = None, einheit: str | None = None,
        beschreibung: str | None = None, parameter: list[dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Bestehende Basisformel ändern (Supersede). Nur die angegebenen Felder werden ersetzt; der
        Diff zeigt alt/neu inkl. beider LaTeX-Darstellungen. Ändert der Ausdruck die Signatur, muss
        `parameter` mitgeliefert werden (jeder genutzte Name deklariert, jeder Parameter genutzt)."""
        e = KatalogEntitaet.FORMELN.value
        zeile = await dienst.aktive_zeile(KatalogEntitaet.FORMELN, name)
        if zeile is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=name,
                           meldungen=[f"keine aktive Formel mit name {name}"])
        alt = zeile.payload
        neuer_ausdruck = ausdruck if ausdruck is not None else alt["ausdruck"]
        neue_einheit = einheit if einheit is not None else alt.get("einheit")
        neue_beschreibung = beschreibung if beschreibung is not None else alt.get("beschreibung")
        neue_parameter = (
            [FormelParameter.model_validate(p) for p in parameter]
            if parameter is not None
            else [FormelParameter.model_validate(p) for p in (alt.get("parameter") or [])]
        )
        formel = Formel(
            name=name, ausdruck=neuer_ausdruck, einheit=neue_einheit,
            beschreibung=neue_beschreibung, parameter=neue_parameter,
        )
        diff = []
        if ausdruck is not None:
            diff.append({"feld": "ausdruck", "alt": alt["ausdruck"], "neu": neuer_ausdruck})
        if einheit is not None:
            diff.append({"feld": "einheit", "alt": alt.get("einheit"), "neu": neue_einheit})
        if beschreibung is not None:
            diff.append({"feld": "beschreibung", "alt": alt.get("beschreibung"), "neu": neue_beschreibung})
        if parameter is not None:
            diff.append({"feld": "parameter", "alt": alt.get("parameter"),
                         "neu": [p.model_dump(mode="json") for p in neue_parameter]})
        entwurf = {
            "name": name, "ausdruck": neuer_ausdruck, "einheit": neue_einheit,
            "beschreibung": neue_beschreibung,
            "parameter": [p.model_dump(mode="json") for p in neue_parameter],
            **_formel_latex(neuer_ausdruck),
            "latex_alt": _formel_latex(alt["ausdruck"]).get("latex"),
        }
        return await _speichern(
            dienst, KatalogBundle(formeln=[formel]),
            aktion="aenderung", entitaet=e, schluessel=name, entwurf=entwurf, diff=diff,
        )

    @tool(response_format="content_and_artifact")
    async def neue_stammdaten_variable(
        name: str, bezeichnung: str, wert: float, beschreibung: str,
        einheit: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue Stammdaten-Variable (ein Satz/Konstante, KONSTANTE-Kaskade) als Entwurf anlegen —
        z. B. ein Lohngruppen-Satz. `beschreibung` ist Pflicht (Bedeutung, welchen Basisformel-
        Parameter der Satz speist, wie er gepflegt wird) — ohne Prosa wird nichts gespeichert. Für
        laufende Änderungen eines Satzes: aendere_stammdaten_wert."""
        vardef = VariableDefinition(
            name=name, bezeichnung=bezeichnung, beschreibung=beschreibung, einheit=einheit,
            aufloesung=[AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=D(wert))],
        )
        bundle = KatalogBundle(
            variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=vardef)]
        )
        entwurf = {"name": name, "bezeichnung": bezeichnung, "wert": D(wert),
                   "einheit": einheit, "gruppe": VariablenGruppe.STAMMDATEN.value}
        return await _speichern(
            dienst, bundle, aktion="neu", entitaet=KatalogEntitaet.VARIABLEN.value,
            schluessel=name, entwurf=entwurf,
        )

    @tool(response_format="content_and_artifact")
    async def aendere_stammdaten_wert(name: str, wert: float) -> tuple[str, dict[str, Any]]:
        """Den KONSTANTE-Wert einer Stammdaten-Variable ändern — die Satzänderung schlechthin
        („Diesel kostet jetzt 1,89"). Supersedet die Variable mit gleicher Kaskade und neuem Wert;
        der Umschlag enthält die Verwendung (where-used) als Impact-Vorschau."""
        e = KatalogEntitaet.VARIABLEN.value
        zeile = await dienst.aktive_zeile(
            KatalogEntitaet.VARIABLEN, name, gruppe=VariablenGruppe.STAMMDATEN.value
        )
        if zeile is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=name,
                           meldungen=[f"keine aktive Stammdaten-Variable mit name {name}"])
        vardef = VariableDefinition.model_validate(
            {"name": name, **{k: v for k, v in zeile.payload.items() if k != "gruppe"}}
        )
        alt_wert: Decimal | None = None
        schritte: list[AufloesungsSchritt] = []
        for s in vardef.aufloesung:
            if s.methode == AufloesungsMethode.KONSTANTE:
                alt_wert = s.konstante
                schritte.append(s.model_copy(update={"konstante": D(wert)}))
            else:
                schritte.append(s)
        if alt_wert is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=name,
                           meldungen=[f"Variable {name} hat keine KONSTANTE-Stufe zum Ändern"])
        neu = vardef.model_copy(update={"aufloesung": schritte})
        bundle = KatalogBundle(
            variablen=[BundleVariable(gruppe=VariablenGruppe.STAMMDATEN, definition=neu)]
        )
        verwendung = await dienst.verwendung_von_variable(name)
        entwurf = {"name": name, "bezeichnung": vardef.bezeichnung, "wert": D(wert),
                   "einheit": vardef.einheit, "verwendung": verwendung}
        diff = [{"feld": "wert", "alt": alt_wert, "neu": D(wert)}]
        return await _speichern(
            dienst, bundle, aktion="aenderung", entitaet=e, schluessel=name,
            entwurf=entwurf, diff=diff,
        )

    @tool(response_format="content_and_artifact")
    async def neue_kontext_variable(
        name: str, bezeichnung: str, beschreibung: str,
        einheit: str | None = None, datentyp: Datentyp | None = None,
        llm_hinweis: str | None = None, default_wert: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue Kontext-Variable (situativer Eingabewert) als Entwurf anlegen. `beschreibung` ist
        Pflicht (Bedeutung, welchen Parameter sie speist, Fallen). Die Kaskade wird serverseitig
        gebaut: mit `llm_hinweis` LANGTEXT+RAG, sonst nur HITL; `default_wert` hängt eine
        KONSTANTE-Rückfallstufe an. `datentyp` default: dezimal."""
        schritte: list[AufloesungsSchritt] = []
        if llm_hinweis:
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.LANGTEXT,
                prompt=f"Aus LV-Langtext/Hinweisen: {bezeichnung} ({einheit or '-'}).",
                konfidenz_schwelle=D("0.75"),
            ))
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.RAG, prompt=llm_hinweis, konfidenz_schwelle=D("0.60")
            ))
        schritte.append(AufloesungsSchritt(methode=AufloesungsMethode.HITL))
        if default_wert is not None:
            schritte.append(AufloesungsSchritt(
                methode=AufloesungsMethode.KONSTANTE, konstante=D(default_wert)
            ))
        vardef = VariableDefinition(
            name=name, bezeichnung=bezeichnung, beschreibung=beschreibung, einheit=einheit,
            datentyp=datentyp if datentyp is not None else Datentyp.DEZIMAL,
            llm_kontext=llm_hinweis, aufloesung=schritte,
        )
        bundle = KatalogBundle(
            variablen=[BundleVariable(gruppe=VariablenGruppe.KONTEXT, definition=vardef)]
        )
        entwurf = {"name": name, "bezeichnung": bezeichnung, "einheit": einheit,
                   "gruppe": VariablenGruppe.KONTEXT.value,
                   "kaskade": [s.methode.value for s in schritte]}
        return await _speichern(
            dienst, bundle, aktion="neu", entitaet=KatalogEntitaet.VARIABLEN.value,
            schluessel=name, entwurf=entwurf,
        )

    # --- Baustoffe / Lieferanten / Preise (batch B, W1–W7) ----------------- #
    @tool(response_format="content_and_artifact")
    async def neuer_baustoff(
        code: str, name: str, rohdichte_t_pro_m3: float, verdichtungsfaktor: float | None = None,
        kategorie: str | None = None, koernung: str | None = None, einheit: str | None = None,
        basispreis_eur_pro_t: float | None = None, basispreis_eur: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neuen Baustoff als Entwurf anlegen (Rohdichte, optional Verdichtungsfaktor, Kategorie,
        Körnung, Einheit, Basispreise)."""
        felder: dict[str, Any] = {"code": code, "name": name, "rohdichte_t_pro_m3": D(rohdichte_t_pro_m3)}
        if verdichtungsfaktor is not None:
            felder["verdichtungsfaktor"] = D(verdichtungsfaktor)
        if kategorie is not None:
            felder["kategorie"] = kategorie
        if koernung is not None:
            felder["koernung"] = koernung
        if einheit is not None:
            felder["einheit"] = einheit
        if basispreis_eur_pro_t is not None:
            felder["basispreis_eur_pro_t"] = D(basispreis_eur_pro_t)
        if basispreis_eur is not None:
            felder["basispreis_eur"] = D(basispreis_eur)
        baustoff = Baustoff.model_validate(felder)
        return await _speichern(
            dienst, KatalogBundle(baustoffe=[baustoff]),
            aktion="neu", entitaet=KatalogEntitaet.BAUSTOFFE.value, schluessel=code,
            entwurf=baustoff.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def aendere_baustoff(
        code: str, aenderungen: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Baustoff-Felder ändern (Delta-Supersede). `aenderungen` enthält nur die zu ändernden Felder
        (z. B. {\"basispreis_eur_pro_t\": 16.20}); der Diff zeigt alt/neu."""
        e = KatalogEntitaet.BAUSTOFFE.value
        zeile = await dienst.aktive_zeile(KatalogEntitaet.BAUSTOFFE, code)
        if zeile is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code,
                           meldungen=[f"kein aktiver Baustoff mit code {code}"])
        r9 = pruefe_aenderungsfelder(KatalogEntitaet.BAUSTOFFE, aenderungen)
        if r9:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code, meldungen=r9)
        merged = {**zeile.payload, **aenderungen}
        baustoff = Baustoff.model_validate({"code": code, **merged})
        return await _speichern(
            dienst, KatalogBundle(baustoffe=[baustoff]),
            aktion="aenderung", entitaet=e, schluessel=code, entwurf=baustoff.model_dump(),
            diff=_diff(zeile.payload, aenderungen),
        )

    @tool(response_format="content_and_artifact")
    async def neuer_lieferant(
        code: str, name: str, standort: str | None = None,
        breitengrad: float | None = None, laengengrad: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neuen Lieferanten als Entwurf anlegen (Standort + optionale Koordinaten)."""
        lief = BundleLieferant(
            code=code, name=name, standort=standort,
            breitengrad=D(breitengrad) if breitengrad is not None else None,
            laengengrad=D(laengengrad) if laengengrad is not None else None,
        )
        return await _speichern(
            dienst, KatalogBundle(lieferanten=[lief]),
            aktion="neu", entitaet=KatalogEntitaet.LIEFERANTEN.value, schluessel=code,
            entwurf=lief.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def aendere_lieferant(
        code: str, aenderungen: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Lieferanten-Felder ändern (Delta-Supersede): name, standort, breitengrad, laengengrad."""
        e = KatalogEntitaet.LIEFERANTEN.value
        zeile = await dienst.aktive_zeile(KatalogEntitaet.LIEFERANTEN, code)
        if zeile is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code,
                           meldungen=[f"kein aktiver Lieferant mit code {code}"])
        r9 = pruefe_aenderungsfelder(KatalogEntitaet.LIEFERANTEN, aenderungen)
        if r9:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code, meldungen=r9)
        merged = {**zeile.payload, **aenderungen}
        lief = BundleLieferant.model_validate({"code": code, **merged})
        return await _speichern(
            dienst, KatalogBundle(lieferanten=[lief]),
            aktion="aenderung", entitaet=e, schluessel=code, entwurf=lief.model_dump(),
            diff=_diff(zeile.payload, aenderungen),
        )

    @tool(response_format="content_and_artifact")
    async def neuer_preis(
        lieferant_code: str, baustoff_code: str, preis_eur_pro_t: float,
        gueltig_ab: str | None = None, gueltig_bis: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue Werkspreis-Zeile als Entwurf anlegen (eine Preiskorrektur ist eine neue Zeile).
        `gueltig_ab`/`gueltig_bis` als ISO-Datum; `gueltig_ab` Standard heute. Warnt, wenn die
        Aktivierung einen offenen Vorgängerpreis schließt."""
        ab = _als_datum(gueltig_ab) or date.today()
        bis = _als_datum(gueltig_bis)
        schluessel = f"{lieferant_code}/{baustoff_code}"
        preis = BundlePreis(
            lieferant_code=lieferant_code, baustoff_code=baustoff_code,
            preis_eur_pro_t=D(preis_eur_pro_t), gueltig_ab=ab, gueltig_bis=bis,
        )
        warnungen: list[str] | None = None
        vorg = await dienst.preis_vorgaenger_offen(lieferant_code, baustoff_code, ab)
        if vorg is not None:
            warnungen = [
                f"Aktivierung schließt den offenen Preis {vorg.preis_eur_pro_t} €/t "
                f"(gültig ab {vorg.gueltig_ab.isoformat()}) zum {(ab - timedelta(days=1)).isoformat()}."
            ]
        entwurf = {"lieferant_code": lieferant_code, "baustoff_code": baustoff_code,
                   "preis_eur_pro_t": D(preis_eur_pro_t), "gueltig_ab": ab, "gueltig_bis": bis}
        return await _speichern(
            dienst, KatalogBundle(preise=[preis]),
            aktion="neu", entitaet="preise", schluessel=schluessel, entwurf=entwurf,
            warnungen=warnungen,
        )

    # --- Maschinen (W3/W4) ------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def neue_maschine(
        code: str, hersteller: str, modell: str, ausfuehrungsart_code: str,
        eigenschaften: dict[str, dict[str, Any]] | None = None,
        leistungsprofile: list[dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue Maschine als Entwurf anlegen. `ausfuehrungsart_code` ist die Geräteklasse (ein Slot).
        `eigenschaften`: {schlüssel: {wert, einheit?}}. `leistungsprofile`:
        [{betriebsart_code, leistung, einheit}] — jede Betriebsart wird geprüft."""
        maschine = Maschine(
            code=code, hersteller=hersteller, modell=modell,
            ausfuehrungsart_code=ausfuehrungsart_code,
            eigenschaften=_bag(eigenschaften),
            leistungsprofile=[_profil(p) for p in (leistungsprofile or [])],
        )
        return await _speichern(
            dienst, KatalogBundle(maschinen=[maschine]),
            aktion="neu", entitaet=KatalogEntitaet.MASCHINEN.value, schluessel=code,
            entwurf=maschine.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def aendere_maschine(
        code: str, aenderungen: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Maschine ändern (Supersede). Skalarfelder (hersteller/modell/ausfuehrungsart_code) als
        Delta; `eigenschaften` werden je Schlüssel gemischt; `leistungsprofile` als ganze Liste
        ersetzt, wenn angegeben. Ein Geräteklassen-Wechsel ist {\"ausfuehrungsart_code\": …}."""
        e = KatalogEntitaet.MASCHINEN.value
        zeile = await dienst.aktive_zeile(KatalogEntitaet.MASCHINEN, code)
        if zeile is None:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code,
                           meldungen=[f"keine aktive Maschine mit code {code}"])
        r9 = pruefe_aenderungsfelder(KatalogEntitaet.MASCHINEN, aenderungen)
        if r9:
            return _fehler(aktion="aenderung", entitaet=e, schluessel=code, meldungen=r9)
        merged = dict(zeile.payload)
        if "eigenschaften" in aenderungen:
            merged["eigenschaften"] = {
                **merged.get("eigenschaften", {}),
                **{k: _wert(v).model_dump() for k, v in aenderungen["eigenschaften"].items()},
            }
        if "leistungsprofile" in aenderungen:
            merged["leistungsprofile"] = [_profil(p).model_dump() for p in aenderungen["leistungsprofile"]]
        for k in ("hersteller", "modell", "ausfuehrungsart_code"):
            if k in aenderungen:
                merged[k] = aenderungen[k]
        maschine = Maschine.model_validate({"code": code, **merged})
        return await _speichern(
            dienst, KatalogBundle(maschinen=[maschine]),
            aktion="aenderung", entitaet=e, schluessel=code, entwurf=maschine.model_dump(),
            diff=_diff(zeile.payload, aenderungen),
        )

    # --- Taxonomien & Mapping (W13–W16) ------------------------------------ #
    @tool(response_format="content_and_artifact")
    async def neue_ausfuehrungsart(
        code: str, name: str, geraetebezug: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Neue Geräteklasse (Ausführungsart) als Entwurf anlegen."""
        aa = Ausführungsart(code=code, name=name, geraetebezug=geraetebezug)
        return await _speichern(
            dienst, KatalogBundle(ausfuehrungsarten=[aa]),
            aktion="neu", entitaet=KatalogEntitaet.AUSFUEHRUNGSARTEN.value, schluessel=code,
            entwurf=aa.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def neue_betriebskategorie(
        code: str, bezeichnung: str, beschreibung: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Neue Betriebskategorie als Entwurf anlegen."""
        kat = Betriebskategorie(code=code, bezeichnung=bezeichnung, beschreibung=beschreibung)
        return await _speichern(
            dienst, KatalogBundle(betriebskategorien=[kat]),
            aktion="neu", entitaet=KatalogEntitaet.BETRIEBSKATEGORIEN.value, schluessel=code,
            entwurf=kat.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def neue_betriebsart(
        code: str, bezeichnung: str, kategorie_code: str, einheit: str | None = None,
        beschreibung: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Neue Betriebsart als Entwurf anlegen; die Betriebskategorie (kategorie_code) wird geprüft."""
        ba = Betriebsart(
            code=code, bezeichnung=bezeichnung, kategorie_code=kategorie_code,
            einheit=einheit, beschreibung=beschreibung,
        )
        return await _speichern(
            dienst, KatalogBundle(betriebsarten=[ba]),
            aktion="neu", entitaet=KatalogEntitaet.BETRIEBSARTEN.value, schluessel=code,
            entwurf=ba.model_dump(),
        )

    @tool(response_format="content_and_artifact")
    async def bauverfahren_zu_leistung(
        leistung_code: str, bauverfahren_codes: list[str]
    ) -> tuple[str, dict[str, Any]]:
        """Die Bauverfahren-Kandidaten einer Leistung setzen (ganze geordnete Liste; erstes = Standard).
        Supersedet das Mapping; der Umschlag zeigt alte vs. neue Reihenfolge."""
        e = KatalogEntitaet.LEISTUNG_BAUVERFAHREN.value
        zeile = await dienst.aktive_zeile(KatalogEntitaet.LEISTUNG_BAUVERFAHREN, leistung_code)
        alt = zeile.payload["bauverfahren_codes"] if zeile is not None else None
        bundle = KatalogBundle(leistung_bauverfahren={leistung_code: bauverfahren_codes})
        entwurf = {"leistung_code": leistung_code, "bauverfahren_codes": bauverfahren_codes, "alt": alt}
        diff = [{"feld": "bauverfahren_codes", "alt": alt, "neu": bauverfahren_codes}]
        return await _speichern(
            dienst, bundle, aktion="aenderung" if alt is not None else "neu",
            entitaet=e, schluessel=leistung_code, entwurf=entwurf, diff=diff,
        )

    # --- Lifecycle (W17) --------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def entwurf_verwerfen(bundle_uuid: str) -> tuple[str, dict[str, Any]]:
        """Einen Entwurfs-Bundle verwerfen (Status verworfen). Der aktive Katalog bleibt
        unberührt. Fehler, wenn der Bundle keine offenen Entwürfe hat."""
        try:
            uuid = UUID(bundle_uuid)
        except ValueError:
            return _fehler(aktion="verwerfen", entitaet="entwurf", schluessel=bundle_uuid,
                           meldungen=[f"kein gültiger bundle_uuid: {bundle_uuid}"])
        try:
            await dienst.bundle_verwerfen(uuid)
        except BundleNichtGefunden:
            return _fehler(aktion="verwerfen", entitaet="entwurf", schluessel=bundle_uuid,
                           meldungen=[f"kein offener Entwurf für bundle_uuid {bundle_uuid}"])
        return _huelle(
            bundle_uuid=uuid, aktion="verwerfen", entitaet="entwurf", schluessel=bundle_uuid,
            bericht=BundleBericht(), entwurf={"verworfen": True},
        )

    return [
        neue_formel,
        aendere_formel,
        neue_stammdaten_variable,
        aendere_stammdaten_wert,
        neue_kontext_variable,
        neuer_baustoff,
        aendere_baustoff,
        neuer_lieferant,
        aendere_lieferant,
        neuer_preis,
        neue_maschine,
        aendere_maschine,
        neue_ausfuehrungsart,
        neue_betriebskategorie,
        neue_betriebsart,
        bauverfahren_zu_leistung,
        entwurf_verwerfen,
    ]


# --------------------------------------------------------------------------- #
# Machine-shape helpers
# --------------------------------------------------------------------------- #
def _wert(roh: dict[str, Any]) -> MaschinenWert:
    """One machine property from {wert, einheit?, beleg?}; a numeric wert becomes Decimal."""
    wert = roh["wert"]
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        wert = D(wert)
    return MaschinenWert(wert=wert, einheit=roh.get("einheit"), beleg=roh.get("beleg"))


def _bag(eigenschaften: dict[str, dict[str, Any]] | None) -> dict[str, MaschinenWert]:
    return {k: _wert(v) for k, v in (eigenschaften or {}).items()}


def _profil(roh: dict[str, Any]) -> Leistungsprofil:
    return Leistungsprofil(
        betriebsart_code=roh["betriebsart_code"], leistung=D(roh["leistung"]),
        einheit=roh["einheit"], eigenschaften=_bag(roh.get("eigenschaften")),
    )
